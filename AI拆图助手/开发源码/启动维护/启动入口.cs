using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
using System.Reflection;
[assembly: AssemblyTitle("AI拆图助手")]
[assembly: AssemblyDescription("AI拆图助手便携启动入口")]
[assembly: AssemblyVersion("0.9.0.0")]
internal static class Launcher {
 [STAThread] static void Main(string[] args) {
  try {
   string root=AppDomain.CurrentDomain.BaseDirectory;
   string script=Path.Combine(root,"开发源码","启动维护","启动AI拆图助手.ps1");
   if(!File.Exists(script))throw new FileNotFoundException("缺少启动文件，请保持程序目录完整。",script);
   string extra="";foreach(string arg in args){if(arg=="-CheckOnly"||arg=="-NoBrowser")extra+=" "+arg;}
   var start=new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"WindowsPowerShell","v1.0","powershell.exe"));
   start.Arguments="-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \""+script+"\""+extra;
   start.WorkingDirectory=root;start.UseShellExecute=false;start.CreateNoWindow=true;start.WindowStyle=ProcessWindowStyle.Hidden;
   Process.Start(start);
  }catch(Exception error){MessageBox.Show(error.Message,"AI拆图助手启动失败",MessageBoxButtons.OK,MessageBoxIcon.Error);}
 }
}
