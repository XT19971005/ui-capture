using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

namespace ShijieLanLauncher
{
    internal sealed class RequestFailure : Exception
    {
        internal readonly int Status;
        internal RequestFailure(int status, string message) : base(message) { Status = status; }
    }

    internal sealed class ProxyServer : IDisposable
    {
        private const long MaximumBody = 276L * 1024 * 1024;
        private static readonly string[] CookieNames = { "shijie_lan_sessionid", "shijie_lan_csrftoken", "shijie_lan_identity" };
        private readonly LauncherConfig config;
        private readonly string origin;
        private readonly string authority;
        private readonly byte[] instanceKey;
        private volatile bool ready;
        private readonly HttpListener listener = new HttpListener();
        private readonly Semaphore slots = new Semaphore(12, 12);
        private readonly object activeLock = new object();
        private readonly HashSet<HttpWebRequest> active = new HashSet<HttpWebRequest>();
        private volatile bool stopped;
        private Thread acceptThread;

        internal ProxyServer(LauncherConfig configuration, int port, byte[] key)
        {
            config = configuration;
            instanceKey = (byte[])key.Clone();
            authority = "127.0.0.1:" + port;
            origin = "http://" + authority;
            listener.Prefixes.Add(origin + "/");
            listener.IgnoreWriteExceptions = false;
        }

        internal void MarkReady() { ready = true; }

        internal void Start()
        {
            ServicePointManager.DefaultConnectionLimit = 16;
            listener.TimeoutManager.HeaderWait = TimeSpan.FromSeconds(15);
            listener.TimeoutManager.EntityBody = TimeSpan.FromSeconds(120);
            listener.TimeoutManager.DrainEntityBody = TimeSpan.FromSeconds(5);
            listener.TimeoutManager.IdleConnection = TimeSpan.FromSeconds(30);
            listener.Start();
            acceptThread = new Thread(AcceptLoop) { IsBackground = true, Name = "LAN local HTTP" };
            acceptThread.Start();
        }

        private void AcceptLoop()
        {
            while (!stopped)
            {
                HttpListenerContext context;
                try { context = listener.GetContext(); }
                catch (HttpListenerException) { break; }
                catch (ObjectDisposedException) { break; }
                if (!slots.WaitOne(0))
                {
                    try { Page(context, 503, "本地入口忙", "当前请求较多，请稍后重试。", false); }
                    catch { }
                    finally { Close(context); }
                    continue;
                }
                ThreadPool.QueueUserWorkItem(delegate
                {
                    try { Handle(context); }
                    catch (RequestFailure ex) { TryPage(context, ex.Status, "请求未完成", ex.Message); }
                    catch (WebException) { TryPage(context, 502, "共享电脑暂时无法连接", "请确认共享电脑已开机且连接同一局域网。原工程和浏览器身份已保留；未自动重发任务。连接恢复后请手动重试。"); }
                    catch (IOException) { }
                    catch (HttpListenerException) { }
                    catch (ObjectDisposedException) { }
                    catch { TryPage(context, 502, "请求未完成", "本地入口无法完成此请求，请稍后重试。未自动重发任务。"); }
                    finally { Close(context); slots.Release(); }
                });
            }
        }

        private void Handle(HttpListenerContext context)
        {
            HttpListenerRequest incoming = context.Request;
            if (incoming.RemoteEndPoint == null || !IPAddress.IsLoopback(incoming.RemoteEndPoint.Address) || !String.Equals(incoming.Headers["Host"], authority, StringComparison.OrdinalIgnoreCase))
                throw new RequestFailure(403, "仅允许本机工作台访问。");
            string method = incoming.HttpMethod.ToUpperInvariant();
            if (method != "GET" && method != "HEAD" && method != "POST" && method != "PUT" && method != "PATCH" && method != "DELETE")
                throw new RequestFailure(405, "此请求方法不可用。");
            string requestOrigin = incoming.Headers["Origin"];
            if (requestOrigin != null && !String.Equals(requestOrigin, origin, StringComparison.Ordinal))
                throw new RequestFailure(403, "请求来源不属于当前工作台。");
            string fetchSite = incoming.Headers["Sec-Fetch-Site"];
            if (fetchSite != null && fetchSite != "same-origin" && fetchSite != "none")
                throw new RequestFailure(403, "禁止跨站访问本地入口。");
            string referer = incoming.Headers["Referer"];
            Uri localReferer = null;
            if (referer != null && (!Uri.TryCreate(referer, UriKind.Absolute, out localReferer) || localReferer.GetLeftPart(UriPartial.Authority) != origin || localReferer.UserInfo.Length != 0))
                throw new RequestFailure(403, "请求来源页面不属于当前工作台。");
            if (method != "GET" && method != "HEAD" && requestOrigin == null && localReferer == null)
                throw new RequestFailure(403, "修改请求缺少当前工作台来源校验。");
            if (incoming.ContentLength64 > MaximumBody) throw new RequestFailure(413, "请求超过 276 MiB，请缩小文件后重试。");
            string target = incoming.RawUrl;
            string path = ValidateTarget(target);
            if (method == "GET" && path == "/_launcher/health")
            {
                Dictionary<string, object> health = new Dictionary<string, object> { { "serviceId", config.ServiceId }, { "version", "1" }, { "ready", ready }, { "buildFingerprint", config.BuildFingerprint } };
                string challenge = incoming.QueryString["challenge"];
                if (challenge != null)
                {
                    if (!Regex.IsMatch(challenge, @"\A[0-9a-f]{64}\z")) throw new RequestFailure(400, "实例验证请求无效。");
                    health["proof"] = Program.InstanceProof(instanceKey, origin, config.ServiceId, config.BuildFingerprint, challenge);
                }
                byte[] bytes = Encoding.UTF8.GetBytes(new JavaScriptSerializer().Serialize(health));
                context.Response.ContentType = "application/json; charset=utf-8";
                context.Response.Headers["Cache-Control"] = "no-store";
                context.Response.ContentLength64 = bytes.Length;
                context.Response.OutputStream.Write(bytes, 0, bytes.Length);
                return;
            }
            if (path == "/_launcher/signed-out" && method == "GET")
            {
                Page(context, 200, "已退出登录", "当前浏览器已退出。远程任务继续运行，自己的本地工程与文件夹授权仍然保留。", true);
                return;
            }
            if (path.StartsWith("/_launcher", StringComparison.OrdinalIgnoreCase)) throw new RequestFailure(404, "入口不存在。");
            if (path == "/login" || path == "/login/")
            {
                if (method != "GET") throw new RequestFailure(405, "请通过重新进入工作台链接登录。");
                Login(context);
                return;
            }
            Proxy(context, target, path, localReferer);
        }

        private static string ValidateTarget(string target)
        {
            if (String.IsNullOrEmpty(target) || target[0] != '/' || target.StartsWith("//", StringComparison.Ordinal) || target.IndexOf('\\') >= 0 || target.IndexOf('#') >= 0 || Regex.IsMatch(target, @"[\x00-\x20\x7f]"))
                throw new RequestFailure(400, "请求路径无效。");
            string path = target.Split('?')[0];
            for (int i = 0; i < 5; i++)
            {
                string decoded;
                try { decoded = Uri.UnescapeDataString(path); }
                catch { throw new RequestFailure(400, "请求路径无效。"); }
                if (decoded == path) break;
                path = decoded;
            }
            if (path.IndexOfAny(new[] { '\\', '%', '?', '#' }) >= 0 || path.Contains("//") || Regex.IsMatch(path, @"[\x00-\x1f\x7f]"))
                throw new RequestFailure(400, "请求路径无效。");
            foreach (string segment in path.Split('/'))
                if (segment == "." || segment == "..") throw new RequestFailure(400, "禁止路径越界。");
            string lower = path.ToLowerInvariant();
            if (lower.StartsWith("/desktop-relay", StringComparison.Ordinal) || lower.StartsWith("/admin", StringComparison.Ordinal) || lower.StartsWith("/api/desktop-service", StringComparison.Ordinal) || lower.StartsWith("/api/users", StringComparison.Ordinal) || lower.StartsWith("/desktop-service", StringComparison.Ordinal) || lower == "/users" || lower.StartsWith("/users/", StringComparison.Ordinal))
                throw new RequestFailure(403, "管理员与接单通道不通过同事入口开放。");
            return path;
        }

        private CookieContainer BrowserCookies(HttpListenerRequest incoming)
        {
            CookieContainer container = new CookieContainer();
            foreach (string name in CookieNames)
            {
                Cookie cookie = incoming.Cookies[config.CookiePrefix + name];
                if (cookie == null || cookie.Value.Length > 8192) continue;
                try { container.Add(config.Server, new Cookie(name, cookie.Value, "/")); }
                catch (CookieException) { }
            }
            return container;
        }

        private CookieContainer AllowedCookies(CookieContainer source)
        {
            CookieContainer target = new CookieContainer();
            foreach (string name in CookieNames)
            {
                Cookie cookie = source.GetCookies(config.Server)[name];
                if (cookie != null && !cookie.Expired)
                    target.Add(config.Server, new Cookie(name, cookie.Value, "/"));
            }
            return target;
        }

        private HttpWebRequest CreateRequest(string target, string method, CookieContainer cookies)
        {
            // The only destination is the validated, embedded private IPv4 address.
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(new Uri(config.Server, target));
            request.Proxy = null;
            request.AllowAutoRedirect = false;
            request.CookieContainer = cookies;
            request.Method = method;
            request.Host = config.Server.Authority;
            request.Timeout = 120000;
            request.ReadWriteTimeout = 120000;
            request.KeepAlive = false;
            request.AllowWriteStreamBuffering = false;
            request.ServicePoint.Expect100Continue = false;
            lock (activeLock)
            {
                if (stopped) throw new ObjectDisposedException("ProxyServer");
                active.Add(request);
            }
            return request;
        }

        private void EndRequest(HttpWebRequest request)
        {
            request.Abort();
            lock (activeLock) active.Remove(request);
        }

        private static HttpWebResponse GetResponse(HttpWebRequest request)
        {
            try { return (HttpWebResponse)request.GetResponse(); }
            catch (WebException ex)
            {
                HttpWebResponse response = ex.Response as HttpWebResponse;
                if (response == null) throw;
                return response;
            }
        }

        private void Login(HttpListenerContext context)
        {
            CookieContainer cookies = BrowserCookies(context.Request);
            HttpWebRequest get = CreateRequest("/login/", "GET", cookies);
            try
            {
                using (HttpWebResponse response = GetResponse(get))
                {
                    CopyCookies(response, context.Response);
                    if (IsRedirect(response.StatusCode))
                    {
                        string destination = LocalLocation(response.Headers["Location"], "/login/");
                        if (destination == "/image-editor.html") { Redirect(context, "/image-editor.html"); return; }
                        throw new RequestFailure(502, "共享电脑返回了异常登录结果，请联系管理员后手动重试。");
                    }
                    if (response.StatusCode != HttpStatusCode.OK)
                    {
                        LoginFailure(context, (int)response.StatusCode);
                        return;
                    }
                }
            }
            finally { EndRequest(get); }
            cookies = AllowedCookies(cookies);
            Cookie csrf = cookies.GetCookies(config.Server)["shijie_lan_csrftoken"];
            if (csrf == null || !Regex.IsMatch(csrf.Value, @"\A[A-Za-z0-9]{32,64}\z"))
                throw new RequestFailure(502, "共享电脑的登录校验信息无效，请联系管理员后手动重试。");
            HttpWebRequest post = CreateRequest("/login/", "POST", cookies);
            try
            {
                post.ContentType = "application/x-www-form-urlencoded";
                post.Headers["Origin"] = config.Server.GetLeftPart(UriPartial.Authority);
                post.Referer = new Uri(config.Server, "/login/").AbsoluteUri;
                byte[] body = Encoding.UTF8.GetBytes("access_code=" + Uri.EscapeDataString(config.AccessCode) + "&csrfmiddlewaretoken=" + Uri.EscapeDataString(csrf.Value) + "&next=%2Fimage-editor.html");
                post.ContentLength = body.Length;
                using (Stream stream = post.GetRequestStream()) stream.Write(body, 0, body.Length);
                using (HttpWebResponse response = GetResponse(post))
                {
                    CopyCookies(response, context.Response);
                    if (IsRedirect(response.StatusCode) && LocalLocation(response.Headers["Location"], "/login/") == "/image-editor.html" && cookies.GetCookies(config.Server)["shijie_lan_sessionid"] != null)
                        Redirect(context, "/image-editor.html");
                    else LoginFailure(context, (int)response.StatusCode);
                }
            }
            finally { EndRequest(post); }
        }

        private static void LoginFailure(HttpListenerContext context, int status)
        {
            string message = status == 429 ? "登录尝试过多，请等待五分钟再手动重试。" : status == 403 ? "当前浏览器无权使用共享服务，请联系管理员。" : "自动登录未成功，请向管理员确认共享服务和启动器版本，再手动重试。";
            Page(context, status == 429 ? 429 : 502, "暂时无法进入工作台", message, true);
        }

        private void Proxy(HttpListenerContext context, string target, string path, Uri referer)
        {
            HttpWebRequest request = CreateRequest(target, context.Request.HttpMethod, BrowserCookies(context.Request));
            try
            {
                CopyRequestHeaders(context.Request, request, referer);
                if (context.Request.HasEntityBody)
                {
                    if (context.Request.ContentLength64 >= 0) request.ContentLength = context.Request.ContentLength64;
                    else request.SendChunked = true;
                    using (Stream output = request.GetRequestStream()) Copy(context.Request.InputStream, output, MaximumBody);
                }
                else if (request.Method == "POST" || request.Method == "PUT" || request.Method == "PATCH") request.ContentLength = 0;
                using (HttpWebResponse response = GetResponse(request))
                {
                    string location = response.Headers["Location"];
                    if (location != null) location = LocalLocation(location, target);
                    CopyCookies(response, context.Response);
                    if ((path == "/logout/" || path == "/logout") && request.Method == "POST" && (int)response.StatusCode >= 200 && (int)response.StatusCode < 400)
                    {
                        Redirect(context, "/_launcher/signed-out");
                        return;
                    }
                    context.Response.StatusCode = (int)response.StatusCode;
                    CopyResponseHeaders(response, context.Response);
                    if (location != null) context.Response.Headers["Location"] = location;
                    if (response.ContentLength >= 0) context.Response.ContentLength64 = response.ContentLength;
                    if (request.Method == "HEAD" || response.StatusCode == HttpStatusCode.NoContent || response.StatusCode == HttpStatusCode.NotModified) return;
                    using (Stream input = response.GetResponseStream()) Copy(input, context.Response.OutputStream, Int64.MaxValue);
                }
            }
            finally { EndRequest(request); }
        }

        private void CopyRequestHeaders(HttpListenerRequest source, HttpWebRequest target, Uri referer)
        {
            HashSet<string> excluded = HopHeaders(source.Headers["Connection"]);
            foreach (string key in source.Headers.AllKeys)
            {
                string name = key.ToLowerInvariant();
                string value = source.Headers[key];
                if (excluded.Contains(name) || name == "cookie" || name == "host" || name == "origin" || name == "referer" || name == "authorization" || name == "content-length" || name == "expect" || name == "date" || name == "forwarded" || name == "x-real-ip" || name.StartsWith("proxy-", StringComparison.Ordinal) || name.StartsWith("x-forwarded-", StringComparison.Ordinal)) continue;
                if (name == "accept") target.Accept = value;
                else if (name == "user-agent") target.UserAgent = value;
                else if (name == "content-type") target.ContentType = value;
                else if (name == "if-modified-since")
                {
                    DateTime date;
                    if (DateTime.TryParse(value, CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal, out date)) target.IfModifiedSince = date;
                }
                else if (name == "range")
                {
                    Match range = Regex.Match(value, @"\Abytes=(\d*)-(\d*)\z");
                    long from, to;
                    if (!range.Success) continue;
                    if (range.Groups[1].Value.Length == 0 && Int64.TryParse(range.Groups[2].Value, out to) && to > 0) target.AddRange(-to);
                    else if (Int64.TryParse(range.Groups[1].Value, out from))
                    {
                        if (range.Groups[2].Value.Length == 0) target.AddRange(from);
                        else if (Int64.TryParse(range.Groups[2].Value, out to) && to >= from) target.AddRange(from, to);
                    }
                }
                else target.Headers[key] = value;
            }
            if (source.Headers["Origin"] != null) target.Headers["Origin"] = config.Server.GetLeftPart(UriPartial.Authority);
            if (referer != null) target.Referer = new Uri(config.Server, referer.PathAndQuery).AbsoluteUri;
        }

        private static HashSet<string> HopHeaders(string connection)
        {
            HashSet<string> result = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade" };
            if (connection != null) foreach (string token in connection.Split(',')) result.Add(token.Trim());
            return result;
        }

        private static void CopyResponseHeaders(HttpWebResponse source, HttpListenerResponse target)
        {
            HashSet<string> excluded = HopHeaders(source.Headers["Connection"]);
            foreach (string key in source.Headers.AllKeys)
            {
                string name = key.ToLowerInvariant();
                if (excluded.Contains(name) || name == "set-cookie" || name == "location" || name == "content-length" || name == "server" || name == "date" || name == "refresh" || name == "content-location" || name.StartsWith("access-control-", StringComparison.Ordinal)) continue;
                if (name == "content-type") target.ContentType = source.ContentType;
                else target.Headers[key] = source.Headers[key];
            }
            target.Headers["Referrer-Policy"] = "no-referrer";
            target.Headers["X-Content-Type-Options"] = "nosniff";
        }

        private string LocalLocation(string value, string requestTarget)
        {
            if (String.IsNullOrEmpty(value) || value.StartsWith("//", StringComparison.Ordinal) || value.IndexOf('\\') >= 0 || Regex.IsMatch(value, @"[\x00-\x20\x7f]"))
                throw new RequestFailure(502, "共享服务返回了不安全的跳转地址。");
            Uri destination;
            if (!Uri.TryCreate(new Uri(config.Server, requestTarget), value, out destination) || destination.Scheme != config.Server.Scheme || destination.Host != config.Server.Host || destination.Port != config.Server.Port || destination.UserInfo.Length != 0)
                throw new RequestFailure(502, "已阻止跳转到共享服务之外的地址。");
            string target = destination.PathAndQuery;
            ValidateTarget(target);
            return target + destination.Fragment;
        }

        private void CopyCookies(HttpWebResponse source, HttpListenerResponse target)
        {
            string[] values = source.Headers.GetValues("Set-Cookie");
            if (values == null) return;
            foreach (string combined in values)
                foreach (string header in Regex.Split(combined, @",(?=\s*[^;,=\s]+\s*=)"))
                {
                    string[] pieces = header.Split(';');
                    int equals = pieces[0].IndexOf('=');
                    if (equals < 1) continue;
                    string name = pieces[0].Substring(0, equals).Trim();
                    if (Array.IndexOf(CookieNames, name) < 0) continue;
                    string value = pieces[0].Substring(equals + 1).Trim();
                    if (value.Length > 8192 || Regex.IsMatch(value, @"[\x00-\x20\x7f]")) continue;
                    StringBuilder mapped = new StringBuilder(config.CookiePrefix + name + "=" + value + "; Path=/");
                    bool httpOnly = name != "shijie_lan_csrftoken";
                    string sameSite = "Lax";
                    for (int i = 1; i < pieces.Length; i++)
                    {
                        string piece = pieces[i].Trim();
                        int split = piece.IndexOf('=');
                        string attribute = (split < 0 ? piece : piece.Substring(0, split)).Trim().ToLowerInvariant();
                        string attributeValue = split < 0 ? "" : piece.Substring(split + 1).Trim();
                        if (attribute == "httponly") httpOnly = true;
                        else if (attribute == "secure") mapped.Append("; Secure");
                        else if (attribute == "samesite" && (attributeValue.Equals("Strict", StringComparison.OrdinalIgnoreCase) || attributeValue.Equals("Lax", StringComparison.OrdinalIgnoreCase) || attributeValue.Equals("None", StringComparison.OrdinalIgnoreCase))) sameSite = attributeValue;
                        else if (attribute == "max-age" && Regex.IsMatch(attributeValue, @"\A-?\d{1,15}\z")) mapped.Append("; Max-Age=" + attributeValue);
                        else if (attribute == "expires")
                        {
                            DateTimeOffset expiry;
                            if (DateTimeOffset.TryParse(attributeValue, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out expiry)) mapped.Append("; Expires=" + expiry.UtcDateTime.ToString("R", CultureInfo.InvariantCulture));
                        }
                    }
                    if (httpOnly) mapped.Append("; HttpOnly");
                    mapped.Append("; SameSite=" + sameSite);
                    target.AppendHeader("Set-Cookie", mapped.ToString());
                }
        }

        private static bool IsRedirect(HttpStatusCode status) { int code = (int)status; return code == 301 || code == 302 || code == 303 || code == 307 || code == 308; }
        private static void Redirect(HttpListenerContext context, string path)
        {
            context.Response.StatusCode = 303;
            context.Response.Headers["Location"] = path;
            context.Response.Headers["Cache-Control"] = "no-store";
            context.Response.ContentLength64 = 0;
        }

        private static void Copy(Stream input, Stream output, long limit)
        {
            byte[] buffer = new byte[65536];
            long total = 0;
            int count;
            while ((count = input.Read(buffer, 0, buffer.Length)) > 0)
            {
                total += count;
                if (total > limit) throw new RequestFailure(413, "请求超过 276 MiB，请缩小文件后重试。");
                output.Write(buffer, 0, count);
            }
        }

        private static void TryPage(HttpListenerContext context, int status, string title, string message)
        {
            try { Page(context, status, title, message, true); }
            catch { }
        }

        private static void Page(HttpListenerContext context, int status, string title, string message, bool link)
        {
            string html = "<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>AI拆图助手</title><style>body{margin:0;padding:12vh 24px;background:#171923;color:#eeedf5;font:16px/1.8 system-ui,sans-serif}main{max-width:540px;margin:auto;padding:30px;background:#252838;border-radius:16px}h1{font-size:25px}a{display:inline-block;margin-top:16px;padding:9px 18px;border-radius:8px;color:white;background:#765bb5;text-decoration:none}p{color:#cecadc}</style><main><h1>" + WebUtility.HtmlEncode(title) + "</h1><p>" + WebUtility.HtmlEncode(message) + "</p>" + (link ? "<a href=\"/login/\">重新进入工作台</a>" : "") + "</main></html>";
            byte[] bytes = Encoding.UTF8.GetBytes(html);
            context.Response.StatusCode = status;
            context.Response.ContentType = "text/html; charset=utf-8";
            context.Response.Headers["Cache-Control"] = "no-store";
            context.Response.Headers["Referrer-Policy"] = "no-referrer";
            context.Response.Headers["X-Frame-Options"] = "DENY";
            context.Response.Headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'";
            context.Response.KeepAlive = false;
            context.Response.ContentLength64 = bytes.Length;
            if (context.Request.HttpMethod != "HEAD") context.Response.OutputStream.Write(bytes, 0, bytes.Length);
        }

        private static void Close(HttpListenerContext context)
        {
            try { context.Response.Close(); }
            catch { }
        }

        public void Dispose()
        {
            lock (activeLock)
            {
                if (stopped) return;
                stopped = true;
                foreach (HttpWebRequest request in active) request.Abort();
            }
            listener.Close();
            if (acceptThread != null && acceptThread != Thread.CurrentThread) acceptThread.Join(1500);
            // In-flight callbacks still release the semaphore after cancellation.
        }
    }
}
