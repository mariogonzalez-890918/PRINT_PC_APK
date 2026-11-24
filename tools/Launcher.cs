using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using System.Text.RegularExpressions;

class Launcher {
    [STAThread] static void Main(string[] args) {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        if(args.Length==2&&args[0]=="--windows-queues"){Environment.ExitCode=WindowsQueueHelper.Run(args[1]);return;}
        Application.Run(new PrintPanel(args.Length>0?args[0]:""));
    }
}

static class WindowsQueueHelper {
    static bool ValidName(string name,string profile){return name!=null&&name.Length<=220&&Regex.IsMatch(name,@"^PRINTER-TAB - [^\r\n]+\["+profile+@"-[0-9a-f]{8}\]$");}
    public static int Run(string path){
        try{
            var file=new FileInfo(path);if(file.Length>1024*1024)throw new Exception("Plan de instalación demasiado grande.");
            var serializer=new JavaScriptSerializer();var plan=serializer.Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));
            string profile=Convert.ToString(plan["profile"]);if(!Regex.IsMatch(profile,"^[0-9a-f]{8}$"))throw new Exception("Perfil no válido.");
            int count=0;
            foreach(var item in (System.Collections.IEnumerable)plan["add"]){
                var row=(Dictionary<string,object>)item;string name=Convert.ToString(row["name"]);Uri uri;
                if(!ValidName(name,profile)||!Uri.TryCreate(Convert.ToString(row["url"]),UriKind.Absolute,out uri)||uri.Scheme!="http"||uri.Host!="127.0.0.1"||uri.Port<20000||uri.Port>=30000||uri.UserInfo.Length>0||uri.Query.Length>0||uri.Fragment.Length>0||!Regex.IsMatch(uri.AbsolutePath,"^/ipp/[0-9a-f]{32}$"))throw new Exception("Cola o dirección de instalación no válida.");
                count++;
            }
            foreach(var item in (System.Collections.IEnumerable)plan["remove"]){if(!ValidName(Convert.ToString(item),profile))throw new Exception("Nombre de cola no válido.");count++;}
            if(count>400)throw new Exception("Demasiadas colas en el plan.");
            string script=@"
[Console]::InputEncoding=[Text.Encoding]::UTF8
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$ErrorActionPreference='Stop'
$plan=[Console]::In.ReadToEnd() | ConvertFrom-Json
$errorsFound=New-Object System.Collections.Generic.List[string]
if (@($plan.add | Where-Object { $_ -ne $null }).Count -gt 0 -and !(Get-Command Add-Printer).Parameters.ContainsKey('IppURL')) { throw 'Esta versión de Windows no admite instalación IPP por esta interfaz. Actualiza Windows 10 a 21H2/22H2 o usa Windows 11 actualizado.' }
foreach ($name in $plan.remove) { try { Remove-Printer -Name ([System.Management.Automation.WildcardPattern]::Escape($name)) -ErrorAction Stop } catch { $errorsFound.Add($name+': '+$_.Exception.Message) } }
foreach ($queue in $plan.add) { try { Add-Printer -Name $queue.name -IppURL $queue.url -ErrorAction Stop } catch { $errorsFound.Add($queue.name+': '+$_.Exception.Message) } }
if ($errorsFound.Count -gt 0) { Write-Output ($errorsFound -join [Environment]::NewLine); exit 1 }
Write-Output 'Colas PRINTER-TAB actualizadas.'
";
            var start=new ProcessStartInfo("powershell.exe","-NoProfile -NonInteractive -EncodedCommand "+Convert.ToBase64String(Encoding.Unicode.GetBytes(script))){UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8};
            using(var process=Process.Start(start)){
                using(var writer=new StreamWriter(process.StandardInput.BaseStream,new UTF8Encoding(false))){writer.Write(serializer.Serialize(plan));}
                var output=process.StandardOutput.ReadToEndAsync();var error=process.StandardError.ReadToEndAsync();
                if(!process.WaitForExit(120000)){process.Kill();throw new Exception("Windows tardó demasiado en instalar las colas. Puede haber cambios parciales; revisa Impresoras y vuelve a sincronizar.");}
                Task.WaitAll(output,error);
                if(process.ExitCode!=0)throw new Exception((output.Result+"\n"+error.Result).Trim());
            }
            return 0;
        }catch(Exception error){MessageBox.Show(error.Message,"PRINTER-TAB · Impresoras Windows",MessageBoxButtons.OK,MessageBoxIcon.Information);return 1;}
    }
}

class PrintPanel : Form {
    readonly string root=AppDomain.CurrentDomain.BaseDirectory;
    readonly string initial;
    readonly JavaScriptSerializer json=new JavaScriptSerializer {MaxJsonLength=8000000};
    Process hub,agent;
    bool working,exiting,ready;
    bool hubConfigured,agentConfigured;
    string email="",lastLogo="",lastIcon="__initial__",consoleUrl="http://localhost:8765",adminToken="";
    readonly Icon defaultIcon;
    readonly Label state=new Label(),account=new Label();
    readonly PictureBox logo=new PictureBox();
    readonly TextBox log=new TextBox();
    readonly NotifyIcon tray=new NotifyIcon();
    Button startHub,startAgent;
    public PrintPanel(string initialMode) {
        initial=initialMode;
        Text="PRINTER-TAB · Panel de impresión";MinimumSize=new Size(740,700);Size=new Size(850,810);
        StartPosition=FormStartPosition.CenterScreen;BackColor=Color.FromArgb(241,245,250);
        Font=new Font("Segoe UI",10);AutoScaleMode=AutoScaleMode.Dpi;
        string ico=Path.Combine(root,"pc","app.ico");if(File.Exists(ico))Icon=new Icon(ico);
        defaultIcon=(Icon)Icon.Clone();
        var layout=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=1,RowCount=9,Padding=new Padding(24)};
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,110));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,50));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,70));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,60));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,70));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,55));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,55));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,75));Controls.Add(layout);
        var header=new Panel {Dock=DockStyle.Fill};logo.Size=new Size(82,82);logo.SizeMode=PictureBoxSizeMode.Zoom;logo.Location=new Point(0,5);logo.Image=DefaultLogo();header.Controls.Add(logo);
        header.Controls.Add(new Label {Text="PRINTER-TAB",Font=new Font("Segoe UI",25,FontStyle.Bold),AutoSize=true,Location=new Point(98,3),ForeColor=Color.FromArgb(18,52,88)});
        header.Controls.Add(new Label {Text="Conecta tus PCs, tablets e impresoras",AutoSize=true,Location=new Point(102,52)});
        account.AutoSize=true;account.Location=new Point(102,77);header.Controls.Add(account);layout.Controls.Add(header,0,0);
        state.Dock=DockStyle.Fill;state.ForeColor=Color.FromArgb(20,100,192);state.Text="Preparando el panel...";layout.Controls.Add(state,0,1);
        var serverRow=new FlowLayoutPanel {Dock=DockStyle.Fill};
        startHub=Button(serverRow,"Iniciar servidor",()=>StartHub());
        Button(serverRow,"Abrir administración",()=>OpenConsole(""));
        Button(serverRow,"Detener servicios",()=>{Stop("agent");Stop("hub");});layout.Controls.Add(serverRow,0,2);
        var agentRow=new FlowLayoutPanel {Dock=DockStyle.Fill};
        startAgent=Button(agentRow,"Iniciar impresión",()=>StartAgent());
        Button(agentRow,"Compartir impresoras",()=>SharePrinters());
        Button(agentRow,"Unir con código",()=>EnrollAgent());layout.Controls.Add(agentRow,0,3);
        var assignmentRow=new FlowLayoutPanel {Dock=DockStyle.Fill};
        Button(assignmentRow,"Asignar a equipos",()=>AssignPrinters(),205);
        Button(assignmentRow,"Imprimir archivo",()=>PrintRemote(),180);
        Button(assignmentRow,"Inventario / Excel",()=>OpenConsole("#inventory"),180);layout.Controls.Add(assignmentRow,0,4);
        var tools=new FlowLayoutPanel {Dock=DockStyle.Fill};
        Button(tools,"Logo / icono / contraseña",()=>OpenConsole("#branding"),240);
        Button(tools,"Minimizar a bandeja",()=>{Hide();tray.Visible=true;},200);
        Button(tools,"Salir",()=>ExitPanel(),100);layout.Controls.Add(tools,0,5);
        layout.RowStyles[6].Height=70;
        var migration=new FlowLayoutPanel {Dock=DockStyle.Fill,AutoScroll=true,WrapContents=false};Button(migration,"Cambiar servidor / restablecer",()=>ResetLocal(),230);Button(migration,"Respaldo / restaurar / limpiar",()=>BackupTools(),240);Button(migration,"Impresoras en Windows",()=>WindowsQueues(),220);layout.Controls.Add(migration,0,6);
        log.Multiline=true;log.ReadOnly=true;log.ScrollBars=ScrollBars.Vertical;log.Dock=DockStyle.Fill;log.BackColor=Color.White;log.Font=new Font("Consolas",9);layout.Controls.Add(log,0,7);
        var footer=new LinkLabel {Dock=DockStyle.Fill,Text="Aplicaciones gestionadas, desarrolladas y administradas por Área de TI GMP · sistemas@grupomipan.com",Padding=new Padding(0,14,0,0)};
        footer.Links.Clear();int pos=footer.Text.IndexOf("sistemas@");footer.Links.Add(pos,footer.Text.Length-pos,"mailto:sistemas@grupomipan.com");footer.LinkClicked+=(s,e)=>Process.Start(new ProcessStartInfo((string)e.Link.LinkData){UseShellExecute=true});layout.Controls.Add(footer,0,8);
        tray.Icon=Icon;tray.Text="PRINTER-TAB";tray.Visible=true;tray.DoubleClick+=(s,e)=>Restore();
        var menu=new ContextMenuStrip();menu.Items.Add("Abrir PRINTER-TAB",null,(s,e)=>Restore());menu.Items.Add("Salir",null,(s,e)=>ExitPanel());tray.ContextMenuStrip=menu;
        FormClosing+=(s,e)=>{if(!exiting){e.Cancel=true;Hide();tray.ShowBalloonTip(2500,"PRINTER-TAB","Continúa en la bandeja de Windows. Usa Salir para detener los componentes.",ToolTipIcon.Info);}};
        Activated+=async(s,e)=>{if(ready&&!working)await LoadStatus();};
        Shown+=async(s,e)=>{try{await LoadStatus();if(initial=="hub")await StartHub();else if(initial=="agent")await StartAgent();}catch(Exception ex){ShowError(ex.Message);}finally{ready=true;}};
    }
    Button Button(Control row,string title,Func<Task> action,int width=190) {
        var b=new Button {Text=title,Width=width,Height=44,Margin=new Padding(0,4,10,4),FlatStyle=FlatStyle.Flat,BackColor=Color.White};
        b.Click+=async(s,e)=>{if(working)return;b.Enabled=false;try{await action();}catch(Exception ex){ShowError(ex.Message);}finally{if(!b.IsDisposed)b.Enabled=true;}};row.Controls.Add(b);return b;
    }
    Button Button(Control row,string title,Action action,int width=190) {return Button(row,title,()=>{action();return Task.FromResult(0);},width);}
    void Restore(){Show();WindowState=FormWindowState.Normal;Activate();}
    void ShowError(string message){Append(message);MessageBox.Show(this,message,"PRINTER-TAB",MessageBoxButtons.OK,MessageBoxIcon.Information);}
    void Append(string line){if(IsDisposed)return;if(InvokeRequired){BeginInvoke(new Action<string>(Append),line);return;}if(log.TextLength>40000)log.Text=log.Text.Substring(log.TextLength-20000);log.AppendText(DateTime.Now.ToString("HH:mm:ss")+"  "+line+Environment.NewLine);}
    ProcessStartInfo Command(string mode) {
        return new ProcessStartInfo(Path.Combine(root,"runtime","python.exe"),"-u \""+Path.Combine(root,"pc","main.py")+"\" "+mode+" --headless") {
            WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,
            RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8
        };
    }
    async Task<string> Bridge(string mode,object data=null) {
        return await Task.Run(()=>{using(var p=new Process {StartInfo=Command(mode)}){
            p.Start();if(data!=null){using(var writer=new StreamWriter(p.StandardInput.BaseStream,new UTF8Encoding(false))){writer.WriteLine(json.Serialize(data));}}else p.StandardInput.Close();
            string output=p.StandardOutput.ReadToEnd(),error=p.StandardError.ReadToEnd();p.WaitForExit();
            if(p.ExitCode!=0)throw new Exception((output+" "+error).Trim());return output.Trim();
        }});
    }
    async Task LoadStatus() {
        working=true;
        try {
            var info=json.Deserialize<Dictionary<string,object>>(await Bridge("status"));
            hubConfigured=(bool)info["hub_configured"];agentConfigured=(bool)info["agent_configured"];
            email=info.ContainsKey("email")?Convert.ToString(info["email"]):"";
            string nextServer=info.ContainsKey("url")?Convert.ToString(info["url"]):"http://localhost:8765";
            if(!String.Equals(consoleUrl,nextServer,StringComparison.OrdinalIgnoreCase))adminToken="";
            consoleUrl=nextServer;
            account.Text=email.Length>0?"Cuenta: "+email:"Únete con correo y código de registro, o inicia el servidor.";
            string custom=info.ContainsKey("logo")?Convert.ToString(info["logo"]):"";
            string customIcon=info.ContainsKey("icon")?Convert.ToString(info["icon"]):"";
            if(customIcon!=lastIcon){ApplyIcon(customIcon);lastIcon=customIcon;}
            if(custom!=lastLogo){Image updated;if(custom.Length==0)updated=DefaultLogo();else using(var stream=new MemoryStream(Convert.FromBase64String(custom))){using(var source=Image.FromStream(stream)){updated=new Bitmap(source);}}var old=logo.Image;logo.Image=updated;if(old!=null)old.Dispose();lastLogo=custom;}
            UpdateState();
        } catch(Exception e){Append(e.Message);state.Text="No se pudo leer la configuración.";}finally{working=false;}
    }
    bool Running(Process p){try{return p!=null&&!p.HasExited;}catch{return false;}}
    Image DefaultLogo(){using(var source=Image.FromFile(Path.Combine(root,"pc","app.png"))){return new Bitmap(source);}}
    void ApplyIcon(string encoded) {
        Icon updated;
        if(encoded.Length==0)updated=(Icon)defaultIcon.Clone();else using(var stream=new MemoryStream(Convert.FromBase64String(encoded))){using(var loaded=new Icon(stream)){updated=(Icon)loaded.Clone();}}
        var previous=Icon;Icon=updated;tray.Icon=updated;if(previous!=null)previous.Dispose();
        string iconPath=Path.Combine(root,"pc","app.ico");
        if(encoded.Length>0){string folder=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"JADPrint","branding");Directory.CreateDirectory(folder);iconPath=Path.Combine(folder,"app.ico");File.WriteAllBytes(iconPath,Convert.FromBase64String(encoded));}
        string[] shortcuts={Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),"PRINTER-TAB.lnk"),Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),"PRINTER-TAB","PRINTER-TAB.lnk"),Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Startup),"PRINTER-TAB.lnk")};
        try {var type=Type.GetTypeFromProgID("WScript.Shell");if(type==null)return;object shell=Activator.CreateInstance(type);try{foreach(string path in shortcuts){if(!File.Exists(path))continue;object link=type.InvokeMember("CreateShortcut",BindingFlags.InvokeMethod,null,shell,new object[]{path});try{link.GetType().InvokeMember("IconLocation",BindingFlags.SetProperty,null,link,new object[]{iconPath+",0"});link.GetType().InvokeMember("Save",BindingFlags.InvokeMethod,null,link,null);}finally{Marshal.FinalReleaseComObject(link);}}}finally{Marshal.FinalReleaseComObject(shell);}}
        catch(Exception e){Append("Icono aplicado al panel; no se pudieron actualizar accesos directos: "+e.Message);}
    }
    void UpdateState(){state.Text=(agentConfigured?"Servidor de la cuenta: "+consoleUrl:"Servidor local: "+(Running(hub)?"activo en http://localhost:8765":"detenido"))+"   ·   Impresión: "+(Running(agent)?"activa":"detenida");startHub.Text=hubConfigured?"Iniciar servidor":"Crear servidor (TI)";startAgent.Text=agentConfigured?"Iniciar impresión":"Unir cliente (código)";}
    async Task ResetLocal(){
        using(var form=new Form {Text="Cambiar servidor / empezar de cero",Size=new Size(620,460),StartPosition=FormStartPosition.CenterParent,Font=Font,FormBorderStyle=FormBorderStyle.FixedDialog,MaximizeBox=false,MinimizeBox=false}){
            var text=new Label {Left=22,Top=18,Width=560,Height=120,Text="Se guardará un respaldo local antes de quitar la configuración. No se borran impresoras de Windows ni datos del servidor remoto.\n\nRevisa primero las colas de impresión: restablecer no cancela documentos ya enviados. Después deberás unir este equipo al servidor nuevo con un código nuevo."};form.Controls.Add(text);
            var scope=new ComboBox {Left=22,Top=146,Width=560,DropDownStyle=ComboBoxStyle.DropDownList};scope.Items.Add("Solo cliente: quitar vinculación y envíos locales");scope.Items.Add("Todo: reiniciar también cuenta y servidor local");scope.SelectedIndex=0;form.Controls.Add(scope);
            form.Controls.Add(new Label {Left=22,Top=193,Width=560,Height=25,Text="Escribe RESTABLECER para confirmar:"});
            var confirm=new TextBox {Left=22,Top=223,Width=560};form.Controls.Add(confirm);
            form.Controls.Add(new Label {Left=22,Top=265,Width=560,Height=60,Text="El servidor nuevo debe estar accesible por su IP de ZeroTier/Radmin y puerto TCP 8765. Los códigos nuevos incluyen esa dirección; no uses localhost para otros equipos."});
            var ok=new Button {Text="Respaldar y restablecer",Left=250,Top=345,Width=210,Height=40,DialogResult=DialogResult.OK};var cancel=new Button {Text="Cancelar",Left=470,Top=345,Width=110,Height=40,DialogResult=DialogResult.Cancel};form.Controls.Add(ok);form.Controls.Add(cancel);form.CancelButton=cancel;
            if(form.ShowDialog(this)!=DialogResult.OK)return;
            if(confirm.Text!="RESTABLECER"){ShowError("No se modificó nada. Escribe RESTABLECER para confirmar.");return;}
            working=true;
            try{
                foreach(var child in new[]{agent,hub})if(Running(child)){child.Kill();if(!child.WaitForExit(5000))throw new Exception("No se pudo detener un servicio. No se restableció la configuración.");}
                var result=json.Deserialize<Dictionary<string,object>>(await Bridge("reset-local",new{scope=scope.SelectedIndex==0?"client":"all",confirmation=confirm.Text}));
                adminToken="";consoleUrl="http://localhost:8765";log.Clear();Append("Configuración restablecida. Respaldo: "+Convert.ToString(result["backup"]));
            }finally{working=false;}
        }
        await LoadStatus();
        MessageBox.Show(this,"En el servidor NUEVO:\n1. Instala PRINTER-TAB y crea la cuenta.\n2. Abre Administración → Servicio central y registro.\n3. Guarda http://IP-VPN-DEL-SERVIDOR:8765 usando su IP de ZeroTier o Radmin.\n4. Genera un código nuevo por equipo.\n\nEn esta PC: Unir con código → Compartir impresoras → Iniciar impresión. En móviles: desvincular y registrar con un código nuevo. El administrador debe volver a asignar permisos.","Pasar al servidor nuevo");
    }
    async Task BackupTools(){
        var choice=Dialog("Respaldo y mudanza de servidor",new[]{"Acción: EXPORTAR, RESTAURAR o LIMPIAR","Confirmación: RESTAURAR o BORRAR ORIGEN (solo al restaurar/limpiar)"},new[]{"EXPORTAR",""},new[]{false,false});
        if(choice==null)return;string action=choice[0].Trim().ToUpperInvariant(),path="";
        if(action!="EXPORTAR"&&action!="RESTAURAR"&&action!="LIMPIAR"){ShowError("Escribe EXPORTAR, RESTAURAR o LIMPIAR.");return;}
        if(action=="RESTAURAR"&&choice[1]!="RESTAURAR"||action=="LIMPIAR"&&choice[1]!="BORRAR ORIGEN"){ShowError("La confirmación no coincide. No se modificó nada.");return;}
        if(action=="EXPORTAR"){
            using(var save=new SaveFileDialog {Title="Guardar respaldo fuera del equipo de origen",Filter="Respaldo PRINTER-TAB (*.zip)|*.zip",FileName="PRINTER-TAB-Respaldo-"+DateTime.Now.ToString("yyyyMMdd-HHmmss")+".zip"}){if(save.ShowDialog(this)!=DialogResult.OK)return;path=save.FileName;}
        }else using(var open=new OpenFileDialog {Title=action=="RESTAURAR"?"Seleccionar respaldo a restaurar":"Seleccionar respaldo verificado antes de limpiar",Filter="Respaldo PRINTER-TAB (*.zip)|*.zip"}){if(open.ShowDialog(this)!=DialogResult.OK)return;path=open.FileName;}
        string detail=action=="LIMPIAR"?"Se eliminarán cuenta, vinculaciones, inventarios y documentos pendientes guardados en esta PC. No se eliminará el archivo de respaldo elegido ni se cancelará la cola de Windows. Copia primero el ZIP al servidor nuevo o a una memoria USB. Se comprobará que corresponde a los datos actuales.":action=="RESTAURAR"?"Se restaurarán cuenta e inventarios en una configuración limpia. Los equipos anteriores quedarán desactivados, los permisos deberán asignarse de nuevo y los trabajos pendientes quedarán detenidos.":"El respaldo contiene cuenta, inventarios, configuración e historial del servidor. No incluye documentos pendientes ni credenciales de cliente. El ZIP contiene datos privados: guárdalo en un lugar protegido y cópialo al equipo nuevo.";
        if(MessageBox.Show(this,detail+"\n\nSe detendrán los servicios iniciados desde este panel. ¿Continuar?","PRINTER-TAB · "+action,MessageBoxButtons.YesNo,MessageBoxIcon.Warning)!=DialogResult.Yes)return;
        working=true;
        try{
            foreach(var child in new[]{agent,hub})if(Running(child)){child.Kill();if(!child.WaitForExit(5000))throw new Exception("No se pudo detener un servicio.");}
            string mode=action=="EXPORTAR"?"export-backup":action=="RESTAURAR"?"restore-backup":"clear-origin";
            var result=json.Deserialize<Dictionary<string,object>>(await Bridge(mode,new{path=path,confirmation=choice[1]}));
            adminToken="";Append(action+": operación completada.");
            MessageBox.Show(this,action=="EXPORTAR"?"Respaldo guardado y verificado:\n"+path+"\n\nCópialo al servidor nuevo. Allí usa RESTAURAR y configura su dirección ZeroTier/Radmin antes de generar códigos nuevos.":Convert.ToString(result["message"]),"PRINTER-TAB");
        }finally{working=false;UpdateState();}
        await LoadStatus();
    }
    async Task WindowsQueues(){
        string action;
        using(var form=new Form {Text="Impresoras de Word, Excel y Chrome",Size=new Size(600,315),StartPosition=FormStartPosition.CenterParent,Font=Font,FormBorderStyle=FormBorderStyle.FixedDialog,MaximizeBox=false,MinimizeBox=false}){
            form.Controls.Add(new Label {Left=20,Top=18,Width=545,Height=70,Text="Instala las impresoras autorizadas como colas de Windows usando su controlador IPP. PRINTER-TAB y su agente deben permanecer abiertos para recibir los documentos y enviarlos al servidor."});
            var mode=new ComboBox {Left=20,Top=105,Width=545,DropDownStyle=ComboBoxStyle.DropDownList};mode.Items.Add("Instalar / actualizar impresoras asignadas");mode.Items.Add("Quitar las impresoras PRINTER-TAB de este perfil");mode.SelectedIndex=0;form.Controls.Add(mode);
            var ok=new Button {Text="Continuar",Left=330,Top=190,Width=110,Height=40,DialogResult=DialogResult.OK};var cancel=new Button {Text="Cancelar",Left=450,Top=190,Width=110,Height=40,DialogResult=DialogResult.Cancel};form.Controls.Add(ok);form.Controls.Add(cancel);form.CancelButton=cancel;
            if(form.ShowDialog(this)!=DialogResult.OK)return;action=mode.SelectedIndex==0?"install":"remove";
        }
        if(action=="install"){
            if(!agentConfigured)await EnrollAgent();if(!agentConfigured)return;
            if(!Running(agent))await StartAgent();
            await Task.Delay(1800);
        }
        var plan=json.Deserialize<Dictionary<string,object>>(await Bridge("windows-queues",new{action=action}));
        int count=0;var names=new List<string>();
        foreach(var item in (System.Collections.IEnumerable)plan["add"]){count++;names.Add("Instalar: "+Convert.ToString(((Dictionary<string,object>)item)["name"]));}
        foreach(var item in (System.Collections.IEnumerable)plan["remove"]){count++;names.Add("Quitar: "+Convert.ToString(item));}
        if(count==0){MessageBox.Show(this,action=="install"?"Las impresoras asignadas ya están instaladas, o no tienes ninguna asignada. Guarda la asignación en el administrador antes de instalar.":"No se encontraron colas PRINTER-TAB de este perfil.","PRINTER-TAB");return;}
        string detail=String.Join("\n",names.GetRange(0,Math.Min(names.Count,10)).ToArray());
        if(MessageBox.Show(this,detail+"\n\nWindows solicitará autorización para modificar estas colas. No se instalarán controladores de terceros. Quitar una cola no cancela documentos ya enviados al controlador de la PC destino. ¿Continuar?","Impresoras en Windows",MessageBoxButtons.YesNo,MessageBoxIcon.Question)!=DialogResult.Yes)return;
        working=true;
        try{
            var start=new ProcessStartInfo(Application.ExecutablePath,"--windows-queues \""+Convert.ToString(plan["path"])+"\""){UseShellExecute=true,Verb="runas"};
            using(var child=Process.Start(start)){await Task.Run(()=>child.WaitForExit());if(child.ExitCode!=0)throw new Exception("Windows no completó todos los cambios. Revisa el mensaje del instalador y vuelve a intentar.");}
            MessageBox.Show(this,"Cambios completados. En Word o Chrome abre Imprimir y selecciona PRINTER-TAB - PC - impresora. Cierra y abre el diálogo de impresión si no se actualiza la lista. Mantén Iniciar impresión activo en esta PC y en la PC de origen.","PRINTER-TAB");
        }catch(System.ComponentModel.Win32Exception error){if(error.NativeErrorCode==1223)Append("Instalación de impresoras cancelada en Windows.");else throw;}
        finally{working=false;}
    }
    Process StartChild(string mode) {
        var p=new Process {StartInfo=Command(mode),EnableRaisingEvents=true};
        p.OutputDataReceived+=(s,e)=>{if(e.Data!=null)Append(e.Data);};p.ErrorDataReceived+=(s,e)=>{if(e.Data!=null)Append(e.Data);};
        p.Exited+=(s,e)=>{if(!IsDisposed)BeginInvoke(new Action(()=>{Append((mode=="hub"?"Servidor":"Agente")+" detenido.");UpdateState();}));};
        p.Start();p.StandardInput.Close();p.BeginOutputReadLine();p.BeginErrorReadLine();return p;
    }
    async Task StartHub() {
        if(Running(hub)){Append("El servidor ya está activo en este panel.");return;}
        if(!hubConfigured){var fields=Dialog("Crear cuenta administradora",new[]{"Correo","Contraseña (4–200 caracteres)","Repetir contraseña"},new[]{"","",""},new[]{false,true,true});if(fields==null)return;
            if(fields[1].Length<4||fields[1].Length>200||fields[1]!=fields[2]){ShowError("Usa de 4 a 200 caracteres y repite la misma contraseña.");return;}
            working=true;try{Append(await Bridge("configure-hub",new{email=fields[0],password=fields[1]}));}finally{working=false;}await LoadStatus();
        }
        hub=StartChild("hub");UpdateState();Append("Usa Abrir administración para gestionar tablets, impresoras y logo.");
    }
    async Task EnrollAgent() {
        if(Running(agent)){ShowError("Detén la impresión antes de cambiar la vinculación.");return;}
        if(agentConfigured&&MessageBox.Show(this,"Esta PC ya está registrada. ¿Unirla con un nuevo código? La vinculación anterior quedará guardada como respaldo.","PRINTER-TAB",MessageBoxButtons.YesNo)!=DialogResult.Yes)return;
        var fields=Dialog("Unir PC · correo y código de registro del servidor",new[]{"Correo de la cuenta","Código de registro completo (PT3...)","Nombre de esta PC"},new[]{email,"",Environment.MachineName},new[]{false,false,false});if(fields==null)return;
        working=true;try{Append(await Bridge("configure-agent",new{email=fields[0],code=fields[1],name=fields[2],replace=agentConfigured}));}finally{working=false;}await LoadStatus();
    }
    async Task StartAgent(){if(Running(agent)){Append("La impresión ya está activa en este panel.");return;}if(!agentConfigured)await EnrollAgent();if(agentConfigured){agent=StartChild("agent");UpdateState();}}
    Dictionary<string,object> AdminPayload(){return new Dictionary<string,object>{{"url",consoleUrl},{"token",adminToken}};}
    IEnumerable<Dictionary<string,object>> Rows(Dictionary<string,object> data,string key){foreach(object item in (System.Collections.IEnumerable)data[key])yield return (Dictionary<string,object>)item;}
    async Task<Dictionary<string,object>> AdminState() {
        if(adminToken.Length>0){try{return json.Deserialize<Dictionary<string,object>>(await Bridge("admin-state",AdminPayload()));}catch{adminToken="";}}
        var fields=Dialog("Administrador · gestión de impresoras",new[]{"Servidor","Correo administrador","Contraseña"},new[]{consoleUrl,email,""},new[]{false,false,true});if(fields==null)return null;
        working=true;try {
            var result=json.Deserialize<Dictionary<string,object>>(await Bridge("admin-login",new{url=fields[0],email=fields[1],password=fields[2]}));
            consoleUrl=fields[0].Trim().TrimEnd('/');adminToken=Convert.ToString(result["token"]);
            return (Dictionary<string,object>)result["state"];
        }finally{working=false;}
    }
    async Task SharePrinters() {
        if(!agentConfigured)await EnrollAgent();if(!agentConfigured)return;
        working=true;try {
            var result=json.Deserialize<Dictionary<string,object>>(await Bridge("publish-client"));
            int count=0;foreach(object printer in (System.Collections.IEnumerable)result["printers"])count++;
            Append("Impresoras de esta PC publicadas: "+count+". Pulsa Asignar impresoras a equipos para elegir los permisos.");
        }finally{working=false;}
        await LoadStatus();
        if(!Running(agent)){agent=StartChild("agent");UpdateState();}
        MessageBox.Show(this,"Las impresoras de esta PC ya aparecen en la cuenta.\n\nAhora pulsa Asignar impresoras a equipos, elige una tablet y marca sus impresoras permitidas.","PRINTER-TAB",MessageBoxButtons.OK,MessageBoxIcon.Information);
    }
    async Task AssignPrinters() {
        var data=await AdminState();if(data==null)return;
        using(var form=new Form {Text="PRINTER-TAB · Asignar impresoras a equipos",Width=840,Height=650,MinimumSize=new Size(680,520),StartPosition=FormStartPosition.CenterParent,Font=Font,Icon=Icon}){
            var layout=new TableLayoutPanel {Dock=DockStyle.Fill,Padding=new Padding(20),ColumnCount=1,RowCount=6};
            foreach(int h in new[]{32,44,45})layout.RowStyles.Add(new RowStyle(SizeType.Absolute,h));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,64));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,55));form.Controls.Add(layout);
            layout.Controls.Add(new Label {Text="Selecciona la PC, tablet o celular y marca sus impresoras permitidas.",Dock=DockStyle.Fill},0,0);
            var tablet=new ComboBox {Dock=DockStyle.Fill,DropDownStyle=ComboBoxStyle.DropDownList};layout.Controls.Add(tablet,0,1);
            var hint=new Label {Dock=DockStyle.Fill,ForeColor=Color.FromArgb(20,100,192)};layout.Controls.Add(hint,0,2);
            var printers=new CheckedListBox {Dock=DockStyle.Fill,CheckOnClick=true,HorizontalScrollbar=true,IntegralHeight=false};layout.Controls.Add(printers,0,3);
            var resultLabel=new Label {Dock=DockStyle.Fill};layout.Controls.Add(resultLabel,0,5);
            var tablets=new List<Dictionary<string,object>>();var printerList=new List<Dictionary<string,object>>();var grants=new List<Dictionary<string,object>>();
            Action selection=()=>{printers.Items.Clear();for(int i=0;i<printerList.Count;i++){
                var p=printerList[i];string pc="PC";foreach(var d in Rows(data,"devices"))if(Convert.ToString(d["id"])==Convert.ToString(p["pc"]))pc=Convert.ToString(d["name"]);
                bool allowed=false;if(tablet.SelectedIndex>=0){string id=Convert.ToString(tablets[tablet.SelectedIndex]["id"]);foreach(var g in grants)if(Convert.ToString(g["tablet"])==id&&Convert.ToString(g["printer"])==Convert.ToString(p["id"]))allowed=true;}
                printers.Items.Add(pc+" · "+Convert.ToString(p["name"])+(Convert.ToInt32(p["available"])==0?" (no disponible)":""),allowed);
            }resultLabel.Text="";};
            Action fill=()=>{tablets.Clear();printerList.Clear();grants.Clear();tablet.Items.Clear();foreach(var d in Rows(data,"devices"))if(Convert.ToString(d["role"])=="tablet"||Convert.ToString(d["role"])=="pc"){tablets.Add(d);tablet.Items.Add((Convert.ToString(d["role"])=="pc"?"PC · ":"Móvil · ")+Convert.ToString(d["name"])+(Convert.ToInt32(d["enabled"])==0?" (desactivada)":""));}foreach(var p in Rows(data,"printers"))printerList.Add(p);foreach(var g in Rows(data,"grants"))grants.Add(g);if(tablets.Count>0)tablet.SelectedIndex=0;else selection();hint.Text=tablets.Count==0?"Registra los equipos con un código de PC o de móvil.":printerList.Count==0?"No hay impresoras: vuelve al panel y pulsa Compartir impresoras en cada PC.":"Equipos registrados: "+tablets.Count+" · Impresoras disponibles para asignar: "+printerList.Count;};
            tablet.SelectedIndexChanged+=(s,e)=>selection();
            var actions=new FlowLayoutPanel {Dock=DockStyle.Fill};layout.Controls.Add(actions,0,4);
            Button(actions,"Guardar asignación",async()=>{
                if(tablet.SelectedIndex<0){MessageBox.Show(form,"Registra y selecciona un equipo primero.");return;}
                string selectedName=tablet.Text;var selected=new List<string>();foreach(int i in printers.CheckedIndices)selected.Add(Convert.ToString(printerList[i]["id"]));
                var request=AdminPayload();request["tablet"]=Convert.ToString(tablets[tablet.SelectedIndex]["id"]);request["printers"]=selected;
                await Bridge("admin-grants",request);data=json.Deserialize<Dictionary<string,object>>(await Bridge("admin-state",AdminPayload()));grants.Clear();foreach(var g in Rows(data,"grants"))grants.Add(g);
                resultLabel.Text="Asignación guardada para "+selectedName+". En la APK pulsa Actualizar impresoras.";
            },190);
            Button(actions,"Actualizar equipos",async()=>{data=json.Deserialize<Dictionary<string,object>>(await Bridge("admin-state",AdminPayload()));fill();},190);
            Button(actions,"Código móvil",async()=>{var request=AdminPayload();request["role"]="tablet";var code=json.Deserialize<Dictionary<string,object>>(await Bridge("admin-code",request));Clipboard.SetText(Convert.ToString(code["registration"]));MessageBox.Show(form,"Código de móvil copiado. En la APK escribe el correo "+Convert.ToString(data["email"])+" y pega el código completo. Vence en 15 minutos y se usa una vez.","Registro de móvil");},170);
            Button(actions,"Código PC",async()=>{var request=AdminPayload();request["role"]="pc";var code=json.Deserialize<Dictionary<string,object>>(await Bridge("admin-code",request));Clipboard.SetText(Convert.ToString(code["registration"]));MessageBox.Show(form,"Código de PC copiado. En el EXE usa Unir con código, el correo "+Convert.ToString(data["email"])+" y pega el código. Vence en 15 minutos.","Registro de PC");},150);
            fill();form.ShowDialog(this);
        }
    }
    async Task PrintRemote() {
        if(!agentConfigured){ShowError("Primero une la PC con correo y código de registro.");return;}
        var data=json.Deserialize<Dictionary<string,object>>(await Bridge("client-state"));
        var list=new List<Dictionary<string,object>>();foreach(var p in Rows(data,"printers"))list.Add(p);
        bool pending=Convert.ToBoolean(data["pending"]);
        using(var form=new Form {Text="PRINTER-TAB · Imprimir en otra PC",Width=680,Height=580,StartPosition=FormStartPosition.CenterParent,Font=Font,Icon=Icon}){
            var panel=new TableLayoutPanel {Dock=DockStyle.Fill,Padding=new Padding(20),ColumnCount=1,RowCount=7};
            foreach(int h in new[]{35,50,55,45,60})panel.RowStyles.Add(new RowStyle(SizeType.Absolute,h));panel.RowStyles.Add(new RowStyle(SizeType.Percent,100));panel.RowStyles.Add(new RowStyle(SizeType.Absolute,45));form.Controls.Add(panel);
            var top=new FlowLayoutPanel {Dock=DockStyle.Fill};top.Controls.Add(new Label {Text="Impresoras asignadas a esta PC",AutoSize=true,Padding=new Padding(0,6,8,0)});panel.Controls.Add(top,0,0);
            var printer=new ComboBox {Dock=DockStyle.Fill,DropDownStyle=ComboBoxStyle.DropDownList};foreach(var p in list)printer.Items.Add(Convert.ToString(p["pc"])+" · "+Convert.ToString(p["name"]));if(list.Count>0)printer.SelectedIndex=0;panel.Controls.Add(printer,0,1);
            var refresh=new Button {Text="Actualizar impresoras",Width=185,Height=30};top.Controls.Add(refresh);refresh.Click+=async(s,e)=>{refresh.Enabled=false;try{var updated=json.Deserialize<Dictionary<string,object>>(await Bridge("client-state"));string selected=printer.SelectedIndex>=0?Convert.ToString(list[printer.SelectedIndex]["id"]):"";list.Clear();printer.Items.Clear();foreach(var p in Rows(updated,"printers")){list.Add(p);printer.Items.Add(Convert.ToString(p["pc"])+" · "+Convert.ToString(p["name"]));}if(list.Count>0)printer.SelectedIndex=0;for(int i=0;i<list.Count;i++)if(Convert.ToString(list[i]["id"])==selected)printer.SelectedIndex=i;if(list.Count==0)MessageBox.Show(form,"No hay impresoras asignadas a esta PC. En Administración marca la impresora de origen y pulsa Guardar asignación. Compartir impresoras publica las instaladas en esta PC; no descarga las de otros equipos.","PRINTER-TAB");}catch(Exception ex){ShowError(ex.Message);}finally{refresh.Enabled=true;}};
            string file="";var choose=new Button {Text="Seleccionar PDF, PNG o JPG",Dock=DockStyle.Fill};var label=new Label {Dock=DockStyle.Fill,Text=pending?"Hay un envío sin confirmar: se reintentará con el mismo identificador.":"Selecciona un documento."};
            choose.Click+=(s,e)=>{using(var dialog=new OpenFileDialog {Filter="Documentos imprimibles|*.pdf;*.png;*.jpg;*.jpeg"})if(dialog.ShowDialog(form)==DialogResult.OK){file=dialog.FileName;label.Text=Path.GetFileName(file);}};choose.Enabled=!pending;panel.Controls.Add(choose,0,2);panel.Controls.Add(label,0,3);
            var copies=new NumericUpDown {Minimum=1,Maximum=20,Value=1,Width=100};if(pending){printer.Enabled=false;copies.Enabled=false;var old=(Dictionary<string,object>)data["pending_job"];var prior=(Dictionary<string,object>)old["options"];label.Text="Envío pendiente: "+Convert.ToString(prior["name"])+" · se conserva el destino original.";if(prior.ContainsKey("copies"))copies.Value=Convert.ToDecimal(prior["copies"]);for(int i=0;i<list.Count;i++)if(Convert.ToString(list[i]["id"])==Convert.ToString(prior["printer"]))printer.SelectedIndex=i;}var row=new FlowLayoutPanel {Dock=DockStyle.Fill};row.Controls.Add(new Label {Text="Copias:",AutoSize=true,Padding=new Padding(0,8,0,0)});row.Controls.Add(copies);panel.Controls.Add(row,0,4);
            var history=new TextBox {ReadOnly=true,Multiline=true,ScrollBars=ScrollBars.Vertical,Dock=DockStyle.Fill};foreach(var job in Rows(data,"jobs"))history.AppendText(Convert.ToString(job["name"])+" · "+Convert.ToString(job["status"])+" · "+Convert.ToString(job["message"])+Environment.NewLine);panel.Controls.Add(history,0,5);
            var actions=new FlowLayoutPanel {Dock=DockStyle.Fill};panel.Controls.Add(actions,0,6);
            Button(actions,pending?"Reintentar pendiente":"Enviar a imprimir",async()=>{
                if(!pending&&(file.Length==0||printer.SelectedIndex<0)){MessageBox.Show(form,"Elige un archivo y una impresora autorizada.");return;}
                if(!pending&&MessageBox.Show(form,"¿Enviar "+Path.GetFileName(file)+" a "+printer.Text+"?","Confirmar impresión",MessageBoxButtons.YesNo)!=DialogResult.Yes)return;
                object options=pending?null:new{printer=Convert.ToString(list[printer.SelectedIndex]["id"]),copies=(int)copies.Value,scale="fit",paper="driver",color="color"};
                var sent=json.Deserialize<Dictionary<string,object>>(await Bridge("client-send",new{path=file,id=Guid.NewGuid().ToString(),options=options}));
                MessageBox.Show(form,"Trabajo registrado: "+Convert.ToString(sent["id"])+". La PC destino debe estar encendida y con su agente activo.","PRINTER-TAB");form.Close();
            },230);
            form.ShowDialog(this);
        }
    }
    void OpenConsole(string suffix){Process.Start(new ProcessStartInfo(consoleUrl.TrimEnd('/')+"/"+suffix){UseShellExecute=true});}
    void Stop(string mode){var p=mode=="hub"?hub:agent;if(!Running(p))return;if(MessageBox.Show(this,"¿Detener "+(mode=="hub"?"el servidor":"la recepción de impresiones")+"? Revisa los trabajos en curso antes de volver a enviarlos.","PRINTER-TAB",MessageBoxButtons.YesNo,MessageBoxIcon.Question)==DialogResult.Yes){p.Kill();p.WaitForExit(3000);UpdateState();}}
    void ExitPanel(){if((Running(hub)||Running(agent))&&MessageBox.Show(this,"Al salir se detendrán el servidor y el agente iniciados desde este panel. ¿Salir?","PRINTER-TAB",MessageBoxButtons.YesNo,MessageBoxIcon.Question)!=DialogResult.Yes)return;exiting=true;if(Running(hub))hub.Kill();if(Running(agent))agent.Kill();tray.Visible=false;tray.Dispose();Close();}
    string[] Dialog(string title,string[] labels,string[] values,bool[] passwords) {
        using(var form=new Form {Text=title,Width=560,Height=180+labels.Length*78,StartPosition=FormStartPosition.CenterParent,FormBorderStyle=FormBorderStyle.FixedDialog,MaximizeBox=false,MinimizeBox=false,Font=Font,Icon=Icon}){
            var inputs=new List<TextBox>();int y=18;
            for(int i=0;i<labels.Length;i++){form.Controls.Add(new Label {Text=labels[i],Left=22,Top=y,Width=490,Height=22});var input=new TextBox {Left=22,Top=y+25,Width=490,Text=values[i],UseSystemPasswordChar=passwords[i],MaxLength=passwords[i]?200:8192};form.Controls.Add(input);inputs.Add(input);y+=78;}
            var ok=new Button {Text="Guardar",Left=302,Top=y+10,Width=100,Height=36,DialogResult=DialogResult.OK};var cancel=new Button {Text="Cancelar",Left=412,Top=y+10,Width=100,Height=36,DialogResult=DialogResult.Cancel};form.Controls.Add(ok);form.Controls.Add(cancel);form.AcceptButton=ok;form.CancelButton=cancel;
            if(form.ShowDialog(this)!=DialogResult.OK)return null;return inputs.ConvertAll(i=>i.Text).ToArray();
        }
    }
}
