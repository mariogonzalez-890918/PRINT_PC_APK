using System;
using System.Diagnostics;
using System.IO;
class Launcher {
    static int Main(string[] args) {
        var root=AppDomain.CurrentDomain.BaseDirectory;
        var mode=args.Length>0 && (args[0]=="hub" || args[0]=="agent") ? " "+args[0] : "";
        try {
            var p=new ProcessStartInfo(Path.Combine(root,"runtime","python.exe"),"-u \""+Path.Combine(root,"pc","main.py")+"\""+mode);
            p.WorkingDirectory=root;
            p.UseShellExecute=false;
            using(var child=Process.Start(p)) {child.WaitForExit();return child.ExitCode;}
        } catch(Exception e) {Console.WriteLine("No se pudo abrir JAD Print: "+e.Message);Console.ReadLine();return 1;}
    }
}
