using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Reflection;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace ShijieLanLauncher
{
    internal sealed class LauncherFailure : Exception
    {
        internal readonly string Kind;
        internal LauncherFailure(string kind, string message) : base(message) { Kind = kind; }
    }

    internal sealed class LauncherConfig
    {
        internal Uri Server;
        internal string AccessCode;
        internal string ServiceId;
        internal string CookiePrefix;
        internal string BuildFingerprint;

        internal static LauncherConfig Load()
        {
            try
            {
                Dictionary<string, object> data;
                using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("launcher.json"))
                {
                    if (stream == null || stream.Length > 16384) throw new InvalidDataException();
                    using (StreamReader reader = new StreamReader(stream, Encoding.UTF8))
                        data = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(reader.ReadToEnd());
                }
                string url = data["serverUrl"] as string;
                string code = data["accessCode"] as string;
                string id = data["serviceId"] as string;
                Match match = Regex.Match(url ?? "", @"\Ahttp://(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3}):(\d{1,5})/?\z", RegexOptions.CultureInvariant);
                if (!match.Success) throw new InvalidDataException();
                int[] octets = new int[4];
                for (int i = 0; i < 4; i++)
                {
                    string piece = match.Groups[i + 1].Value;
                    octets[i] = Int32.Parse(piece);
                    if (octets[i] > 255 || (piece.Length > 1 && piece[0] == '0')) throw new InvalidDataException();
                }
                int port = Int32.Parse(match.Groups[5].Value);
                bool privateAddress = octets[0] == 10 || (octets[0] == 172 && octets[1] >= 16 && octets[1] <= 31) || (octets[0] == 192 && octets[1] == 168);
                if (!privateAddress || port < 1 || port > 65535 || String.IsNullOrWhiteSpace(code) || code.Length > 80 || code.IndexOfAny(new[] { '\r', '\n', '\0' }) >= 0 || !Regex.IsMatch(id ?? "", @"\A[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\z"))
                    throw new InvalidDataException();
                string hash;
                using (SHA256 sha = SHA256.Create())
                    hash = BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(id))).Replace("-", "").ToLowerInvariant();
                string fingerprint;
                using (SHA256 sha = SHA256.Create())
                using (FileStream executable = File.OpenRead(Assembly.GetExecutingAssembly().Location))
                    fingerprint = BitConverter.ToString(sha.ComputeHash(executable)).Replace("-", "").ToLowerInvariant();
                return new LauncherConfig { Server = new Uri(url.TrimEnd('/') + "/"), AccessCode = code, ServiceId = id, CookiePrefix = "ailan_" + hash.Substring(0, 24) + "_", BuildFingerprint = fingerprint };
            }
            catch { throw new LauncherFailure("Configuration", "启动器配置无效，请向共享电脑管理员索取新的启动器。"); }
        }
    }

    internal static class Program
    {
        internal const int DefaultPort = 19219;
        internal static bool Headless;
        private static int port = DefaultPort;
        private static bool isolated;

        [STAThread]
        private static int Main(string[] args)
        {
            Headless = Array.IndexOf(args, "--headless") >= 0;
            try
            {
                ParseArguments(args);
                LauncherConfig config = LauncherConfig.Load();
                string origin = "http://127.0.0.1:" + port;
                string localData = Environment.GetEnvironmentVariable("LOCALAPPDATA");
                if (String.IsNullOrWhiteSpace(localData)) localData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                string directory = Path.Combine(localData, "AI拆图助手", "本地入口");
                if (isolated || Headless) directory = Path.Combine(directory, "测试端口_" + port);
                string binding = Path.Combine(directory, "binding.json");
                string keyPath = Path.Combine(directory, "instance.key");
                ProtectDirectory(directory);
                bool created;
                using (Mutex mutex = new Mutex(true, @"Local\ShijieLanLauncher_" + port, out created))
                {
                    if (!created)
                    {
                        CheckBinding(binding, config.ServiceId);
                        if (!ExistingInstance(origin, config, keyPath))
                            throw new LauncherFailure("PortBusy", "无法验证本地端口中的程序身份。若已打开旧版启动器，请先在托盘退出旧启动器后重试。");
                        if (!Headless) OpenBrowser(origin + "/image-editor.html");
                        return 0;
                    }
                    try
                    {
                        CheckBinding(binding, config.ServiceId);
                        byte[] instanceKey = RandomBytes();
                        using (ProxyServer server = new ProxyServer(config, port, instanceKey))
                        {
                            try { server.Start(); }
                            catch (HttpListenerException)
                            {
                                if (!ExistingInstance(origin, config, keyPath))
                                    throw new LauncherFailure("PortBusy", "本地端口 " + port + " 已被其他程序占用，或系统不允许监听，请关闭占用程序后重试。");
                                if (!Headless) OpenBrowser(origin + "/image-editor.html");
                                return 0;
                            }
                            StoreInstanceKey(keyPath, instanceKey);
                            if (!File.Exists(binding))
                            {
                                using (FileStream stream = new FileStream(binding, FileMode.CreateNew, FileAccess.Write, FileShare.Read))
                                using (StreamWriter writer = new StreamWriter(stream, new UTF8Encoding(false)))
                                    writer.Write(new JavaScriptSerializer().Serialize(new { serviceId = config.ServiceId }));
                            }
                            server.MarkReady();
                            if (Headless)
                            {
                                using (ManualResetEvent stop = new ManualResetEvent(false))
                                {
                                    Console.CancelKeyPress += delegate(object sender, ConsoleCancelEventArgs e) { e.Cancel = true; stop.Set(); };
                                    stop.WaitOne();
                                }
                            }
                            else
                            {
                                Application.EnableVisualStyles();
                                Application.SetCompatibleTextRenderingDefault(false);
                                using (LauncherTray tray = new LauncherTray(origin, server))
                                {
                                    OpenBrowser(origin + "/image-editor.html");
                                    Application.Run(tray);
                                }
                            }
                        }
                    }
                    finally { mutex.ReleaseMutex(); }
                }
                return 0;
            }
            catch (LauncherFailure ex) { Report(ex.Kind, ex.Message); return 1; }
            catch { Report("Startup", "本地入口未能启动，请确认当前用户可以写入本地应用目录后重试。"); return 1; }
        }

        private static void ParseArguments(string[] args)
        {
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--headless") continue;
                if (args[i] == "--port" && i + 1 < args.Length && !isolated && Int32.TryParse(args[++i], out port) && port >= 1024 && port <= 65535)
                { isolated = true; continue; }
                throw new LauncherFailure("Arguments", "启动参数无效。");
            }
        }

        private static void CheckBinding(string path, string serviceId)
        {
            if (!File.Exists(path)) return;
            try
            {
                if (new FileInfo(path).Length > 4096) throw new InvalidDataException();
                Dictionary<string, object> value = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(path, Encoding.UTF8));
                if ((value["serviceId"] as string) == serviceId) return;
            }
            catch { throw new LauncherFailure("ProfileBinding", "本地入口绑定记录无法读取。请联系管理员处理，已有工程和浏览器身份仍保留。"); }
            throw new LauncherFailure("ProfileBinding", "此电脑的本地入口已绑定另一套共享服务。为避免账号和文件夹授权混用，无法切换。请使用原服务的启动器，或联系管理员处理。");
        }

        private static bool ExistingInstance(string origin, LauncherConfig config, string keyPath)
        {
            for (int attempt = 0; attempt < 3; attempt++)
            {
                try
                {
                    if (!PrivateKeyFile(keyPath)) throw new InvalidDataException();
                    byte[] key = File.ReadAllBytes(keyPath);
                    if (key.Length != 32) throw new InvalidDataException();
                    string challenge = Hex(RandomBytes());
                    HttpWebRequest request = (HttpWebRequest)WebRequest.Create(origin + "/_launcher/health?challenge=" + challenge);
                    request.Proxy = null;
                    request.AllowAutoRedirect = false;
                    request.Timeout = 1000;
                    request.ReadWriteTimeout = 1000;
                    request.KeepAlive = false;
                    using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                    {
                        if (response.StatusCode != HttpStatusCode.OK) return false;
                        using (Stream stream = response.GetResponseStream())
                        using (MemoryStream bytes = new MemoryStream())
                        {
                            byte[] buffer = new byte[4097];
                            int count;
                            while ((count = stream.Read(buffer, 0, buffer.Length)) > 0)
                            {
                                if (bytes.Length + count > 4096) return false;
                                bytes.Write(buffer, 0, count);
                            }
                            Dictionary<string, object> value = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(Encoding.UTF8.GetString(bytes.ToArray()));
                            if ((value["serviceId"] as string) != config.ServiceId || (value["version"] as string) != "1" || !Object.Equals(value["ready"], true)) throw new InvalidDataException();
                            string fingerprint = value["buildFingerprint"] as string;
                            string proof = value["proof"] as string;
                            if (!Regex.IsMatch(fingerprint ?? "", @"\A[0-9a-f]{64}\z") || !ProofEquals(InstanceProof(key, origin, config.ServiceId, fingerprint, challenge), proof)) return false;
                            if (fingerprint != config.BuildFingerprint)
                                throw new LauncherFailure("RestartRequired", "检测到已运行的启动器版本或共享配置与当前文件不同。请先保存正在编辑的工程，再从托盘退出旧启动器并重新打开当前文件；远程任务不会因此取消。");
                            return true;
                        }
                    }
                }
                catch (LauncherFailure) { throw; }
                catch { if (attempt < 2) Thread.Sleep(200); }
            }
            return false;
        }

        private static SecurityIdentifier CurrentUser()
        {
            using (WindowsIdentity identity = WindowsIdentity.GetCurrent()) return identity.User;
        }

        private static SecurityIdentifier[] PrivatePrincipals()
        {
            return new[] { CurrentUser(), new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null), new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null) };
        }

        private static void ProtectDirectory(string path)
        {
            DirectoryInfo directory = Directory.CreateDirectory(path);
            if ((directory.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new LauncherFailure("ProfileSecurity", "本地入口身份目录不能使用目录链接，请联系管理员处理。");
            DirectorySecurity security = new DirectorySecurity();
            security.SetOwner(CurrentUser());
            security.SetAccessRuleProtection(true, false);
            foreach (SecurityIdentifier sid in PrivatePrincipals())
                security.AddAccessRule(new FileSystemAccessRule(sid, FileSystemRights.FullControl, InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit, PropagationFlags.None, AccessControlType.Allow));
            directory.SetAccessControl(security);
        }

        private static bool PrivateKeyFile(string path)
        {
            try
            {
                FileInfo file = new FileInfo(path);
                if (!file.Exists || file.Length != 32 || (file.Attributes & FileAttributes.ReparsePoint) != 0) return false;
                FileSecurity security = file.GetAccessControl(AccessControlSections.Access | AccessControlSections.Owner);
                if (!security.AreAccessRulesProtected || !CurrentUser().Equals(security.GetOwner(typeof(SecurityIdentifier)))) return false;
                SecurityIdentifier[] principals = PrivatePrincipals();
                foreach (FileSystemAccessRule rule in security.GetAccessRules(true, true, typeof(SecurityIdentifier)))
                    if (rule.AccessControlType == AccessControlType.Allow && Array.IndexOf(principals, rule.IdentityReference as SecurityIdentifier) < 0) return false;
                return true;
            }
            catch { return false; }
        }

        private static void StoreInstanceKey(string path, byte[] key)
        {
            if (File.Exists(path) && !PrivateKeyFile(path))
                throw new LauncherFailure("ProfileSecurity", "本地入口的实例密钥权限或内容无效，请联系管理员处理；已有工程与浏览器身份保留。");
            FileSecurity security = new FileSecurity();
            security.SetOwner(CurrentUser());
            security.SetAccessRuleProtection(true, false);
            foreach (SecurityIdentifier sid in PrivatePrincipals())
                security.AddAccessRule(new FileSystemAccessRule(sid, FileSystemRights.FullControl, AccessControlType.Allow));
            // Apply the protected ACL atomically at creation; ordinary write handles
            // cannot reliably change owner/DACL later with SetAccessControl.
            using (FileStream stream = new FileStream(path, FileMode.Create, FileSystemRights.Write, FileShare.Read, 4096, FileOptions.None, security))
            {
                stream.Write(key, 0, key.Length);
                stream.Flush(true);
            }
        }

        private static byte[] RandomBytes()
        {
            byte[] value = new byte[32];
            using (RandomNumberGenerator random = RandomNumberGenerator.Create()) random.GetBytes(value);
            return value;
        }

        private static string Hex(byte[] value) { return BitConverter.ToString(value).Replace("-", "").ToLowerInvariant(); }

        internal static string InstanceProof(byte[] key, string origin, string serviceId, string fingerprint, string challenge)
        {
            byte[] message = Encoding.UTF8.GetBytes("shijie-launcher-instance-v1\n" + origin + "\n" + serviceId + "\n" + fingerprint + "\n" + challenge);
            using (HMACSHA256 hmac = new HMACSHA256(key)) return Hex(hmac.ComputeHash(message));
        }

        private static bool ProofEquals(string expected, string received)
        {
            if (received == null || received.Length != expected.Length) return false;
            int difference = 0;
            for (int i = 0; i < expected.Length; i++) difference |= expected[i] ^ received[i];
            return difference == 0;
        }

        internal static void OpenBrowser(string url)
        {
            string[] roots = { Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) };
            string[] browsers = { @"Microsoft\Edge\Application\msedge.exe", @"Google\Chrome\Application\chrome.exe" };
            foreach (string browser in browsers)
                foreach (string root in roots)
                {
                    string path = Path.Combine(root, browser);
                    if (!File.Exists(path)) continue;
                    try
                    {
                        Process.Start(new ProcessStartInfo(path, "--new-window \"" + url + "\"") { UseShellExecute = false });
                        return;
                    }
                    catch { }
                }
            throw new LauncherFailure("Browser", "未找到可用的 Microsoft Edge 或 Google Chrome，请安装其中一个浏览器后重试。");
        }

        internal static void Report(string kind, string message)
        {
            if (Headless) Console.Error.WriteLine(kind + ": " + message);
            else MessageBox.Show(message, "AI拆图助手 · 本地入口", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    internal sealed class LauncherTray : ApplicationContext
    {
        private readonly NotifyIcon icon;
        private readonly ProxyServer server;
        internal LauncherTray(string origin, ProxyServer proxy)
        {
            server = proxy;
            ContextMenuStrip menu = new ContextMenuStrip();
            EventHandler open = delegate
            {
                try { Program.OpenBrowser(origin + "/image-editor.html"); }
                catch (LauncherFailure ex) { Program.Report(ex.Kind, ex.Message); }
            };
            menu.Items.Add("打开工作台", null, open);
            menu.Items.Add("退出启动器（远程任务继续）", null, delegate { ExitThread(); });
            icon = new NotifyIcon { Icon = SystemIcons.Application, Text = "AI拆图助手 · 本地入口", ContextMenuStrip = menu, Visible = true };
            icon.DoubleClick += open;
        }
        protected override void ExitThreadCore() { server.Dispose(); icon.Visible = false; base.ExitThreadCore(); }
        protected override void Dispose(bool disposing)
        {
            if (disposing) { icon.Visible = false; icon.ContextMenuStrip.Dispose(); icon.Dispose(); }
            base.Dispose(disposing);
        }
    }
}
