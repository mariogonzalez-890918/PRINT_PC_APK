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

class Launcher {
    [STAThread] static void Main(string[] args) {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new PrintPanel(args.Length>0?args[0]:""));
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
        var layout=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=1,RowCount=8,Padding=new Padding(24)};
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,110));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,50));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,70));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,60));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute,70));
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
        Button(serverRow,"Detener servidor",()=>Stop("hub"));layout.Controls.Add(serverRow,0,2);
        var agentRow=new FlowLayoutPanel {Dock=DockStyle.Fill};
        startAgent=Button(agentRow,"Iniciar impresión",()=>StartAgent());
        Button(agentRow,"Compartir impresoras",()=>SharePrinters());
        Button(agentRow,"Vincular por código",()=>EnrollAgent());layout.Controls.Add(agentRow,0,3);
        var assignmentRow=new FlowLayoutPanel {Dock=DockStyle.Fill};
        Button(assignmentRow,"Asignar impresoras a tablets",()=>AssignPrinters(),280);
        Button(assignmentRow,"Detener impresión",()=>Stop("agent"));layout.Controls.Add(assignmentRow,0,4);
        var tools=new FlowLayoutPanel {Dock=DockStyle.Fill};
        Button(tools,"Logo / icono / contraseña",()=>OpenConsole("#branding"),240);
        Button(tools,"Minimizar a bandeja",()=>{Hide();tray.Visible=true;},200);
        Button(tools,"Salir",()=>ExitPanel(),100);layout.Controls.Add(tools,0,5);
        log.Multiline=true;log.ReadOnly=true;log.ScrollBars=ScrollBars.Vertical;log.Dock=DockStyle.Fill;log.BackColor=Color.White;log.Font=new Font("Consolas",9);layout.Controls.Add(log,0,6);
        var footer=new LinkLabel {Dock=DockStyle.Fill,Text="Aplicaciones gestionadas, desarrolladas y administradas por Área de TI GMP · sistemas@grupomipan.com",Padding=new Padding(0,14,0,0)};
        footer.Links.Clear();int pos=footer.Text.IndexOf("sistemas@");footer.Links.Add(pos,footer.Text.Length-pos,"mailto:sistemas@grupomipan.com");footer.LinkClicked+=(s,e)=>Process.Start(new ProcessStartInfo((string)e.Link.LinkData){UseShellExecute=true});layout.Controls.Add(footer,0,7);
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
            consoleUrl=info.ContainsKey("url")?Convert.ToString(info["url"]):"http://localhost:8765";
            account.Text=email.Length>0?"Cuenta local: "+email:"Configura el servidor o vincula esta PC para comenzar.";
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
    void UpdateState(){state.Text="Servidor: "+(Running(hub)?"activo en http://localhost:8765":"detenido en este panel")+"   ·   Impresión: "+(Running(agent)?"activa":"detenida en este panel");startHub.Text=hubConfigured?"Iniciar servidor":"Crear cuenta / servidor";startAgent.Text=agentConfigured?"Iniciar impresión":"Vincular e iniciar";}
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
        if(agentConfigured){ShowError("Esta PC ya está vinculada. Pulsa Iniciar impresión.");return;}
        var fields=Dialog("Vincular PC · genera un código de PC en la consola",new[]{"Servidor (URL)","Correo de la cuenta","Código de PC","Nombre de esta PC"},new[]{"http://localhost:8765",email,"",Environment.MachineName},new[]{false,false,false,false});if(fields==null)return;
        working=true;try{Append(await Bridge("configure-agent",new{url=fields[0],email=fields[1],code=fields[2],name=fields[3]}));}finally{working=false;}await LoadStatus();
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
        var info=await AdminState();if(info==null)return;
        working=true;try {
            var request=AdminPayload();request["name"]=Environment.MachineName;
            var result=json.Deserialize<Dictionary<string,object>>(await Bridge("publish-printers",request));
            int count=0;foreach(object printer in (System.Collections.IEnumerable)result["printers"])count++;
            Append("Impresoras de esta PC publicadas: "+count+". Pulsa Asignar impresoras a tablets para elegir los permisos.");
        }finally{working=false;}
        await LoadStatus();
        if(!Running(agent)){agent=StartChild("agent");UpdateState();}
        MessageBox.Show(this,"Las impresoras de esta PC ya aparecen en la cuenta.\n\nAhora pulsa Asignar impresoras a tablets, elige una tablet y marca sus impresoras permitidas.","PRINTER-TAB",MessageBoxButtons.OK,MessageBoxIcon.Information);
    }
    async Task AssignPrinters() {
        var data=await AdminState();if(data==null)return;
        using(var form=new Form {Text="PRINTER-TAB · Asignar impresoras a tablets",Width=840,Height=650,MinimumSize=new Size(680,520),StartPosition=FormStartPosition.CenterParent,Font=Font,Icon=Icon}){
            var layout=new TableLayoutPanel {Dock=DockStyle.Fill,Padding=new Padding(20),ColumnCount=1,RowCount=6};
            foreach(int h in new[]{32,44,45})layout.RowStyles.Add(new RowStyle(SizeType.Absolute,h));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,64));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,55));form.Controls.Add(layout);
            layout.Controls.Add(new Label {Text="Selecciona la tablet y marca las impresoras que podrá utilizar.",Dock=DockStyle.Fill},0,0);
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
            Action fill=()=>{tablets.Clear();printerList.Clear();grants.Clear();tablet.Items.Clear();foreach(var d in Rows(data,"devices"))if(Convert.ToString(d["role"])=="tablet"){tablets.Add(d);tablet.Items.Add(Convert.ToString(d["name"])+(Convert.ToInt32(d["enabled"])==0?" (desactivada)":""));}foreach(var p in Rows(data,"printers"))printerList.Add(p);foreach(var g in Rows(data,"grants"))grants.Add(g);if(tablets.Count>0)tablet.SelectedIndex=0;else selection();hint.Text=tablets.Count==0?"Primero vincula una tablet con el botón Vincular tablet.":printerList.Count==0?"No hay impresoras: vuelve al panel y pulsa Compartir impresoras en cada PC.":"Tablets vinculadas: "+tablets.Count+" · Impresoras disponibles para asignar: "+printerList.Count;};
            tablet.SelectedIndexChanged+=(s,e)=>selection();
            var actions=new FlowLayoutPanel {Dock=DockStyle.Fill};layout.Controls.Add(actions,0,4);
            Button(actions,"Guardar asignación",async()=>{
                if(tablet.SelectedIndex<0){MessageBox.Show(form,"Vincula y selecciona una tablet primero.");return;}
                string selectedName=tablet.Text;var selected=new List<string>();foreach(int i in printers.CheckedIndices)selected.Add(Convert.ToString(printerList[i]["id"]));
                var request=AdminPayload();request["tablet"]=Convert.ToString(tablets[tablet.SelectedIndex]["id"]);request["printers"]=selected;
                await Bridge("admin-grants",request);data=json.Deserialize<Dictionary<string,object>>(await Bridge("admin-state",AdminPayload()));grants.Clear();foreach(var g in Rows(data,"grants"))grants.Add(g);
                resultLabel.Text="Asignación guardada para "+selectedName+". En la APK pulsa Actualizar impresoras.";
            },190);
            Button(actions,"Actualizar equipos",async()=>{data=json.Deserialize<Dictionary<string,object>>(await Bridge("admin-state",AdminPayload()));fill();},190);
            Button(actions,"Vincular tablet",async()=>{var code=json.Deserialize<Dictionary<string,object>>(await Bridge("admin-code",AdminPayload()));MessageBox.Show(form,"En la APK introduce:\nServidor: "+consoleUrl+"\nCorreo: "+Convert.ToString(data["email"])+"\nCódigo: "+Convert.ToString(code["code"])+"\n\nEl código vence en 15 minutos. Si estás en la PC servidor, cambia localhost por su dirección IP en la tablet. Después pulsa Actualizar equipos.","Vincular tablet",MessageBoxButtons.OK,MessageBoxIcon.Information);},170);
            fill();form.ShowDialog(this);
        }
    }
    void OpenConsole(string suffix){Process.Start(new ProcessStartInfo(consoleUrl.TrimEnd('/')+"/"+suffix){UseShellExecute=true});}
    void Stop(string mode){var p=mode=="hub"?hub:agent;if(!Running(p))return;if(MessageBox.Show(this,"¿Detener "+(mode=="hub"?"el servidor":"la recepción de impresiones")+"? Revisa los trabajos en curso antes de volver a enviarlos.","PRINTER-TAB",MessageBoxButtons.YesNo,MessageBoxIcon.Question)==DialogResult.Yes){p.Kill();p.WaitForExit(3000);UpdateState();}}
    void ExitPanel(){if((Running(hub)||Running(agent))&&MessageBox.Show(this,"Al salir se detendrán el servidor y el agente iniciados desde este panel. ¿Salir?","PRINTER-TAB",MessageBoxButtons.YesNo,MessageBoxIcon.Question)!=DialogResult.Yes)return;exiting=true;if(Running(hub))hub.Kill();if(Running(agent))agent.Kill();tray.Visible=false;tray.Dispose();Close();}
    string[] Dialog(string title,string[] labels,string[] values,bool[] passwords) {
        using(var form=new Form {Text=title,Width=560,Height=180+labels.Length*78,StartPosition=FormStartPosition.CenterParent,FormBorderStyle=FormBorderStyle.FixedDialog,MaximizeBox=false,MinimizeBox=false,Font=Font,Icon=Icon}){
            var inputs=new List<TextBox>();int y=18;
            for(int i=0;i<labels.Length;i++){form.Controls.Add(new Label {Text=labels[i],Left=22,Top=y,Width=490,Height=22});var input=new TextBox {Left=22,Top=y+25,Width=490,Text=values[i],UseSystemPasswordChar=passwords[i],MaxLength=passwords[i]?200:300};form.Controls.Add(input);inputs.Add(input);y+=78;}
            var ok=new Button {Text="Guardar",Left=302,Top=y+10,Width=100,Height=36,DialogResult=DialogResult.OK};var cancel=new Button {Text="Cancelar",Left=412,Top=y+10,Width=100,Height=36,DialogResult=DialogResult.Cancel};form.Controls.Add(ok);form.Controls.Add(cancel);form.AcceptButton=ok;form.CancelButton=cancel;
            if(form.ShowDialog(this)!=DialogResult.OK)return null;return inputs.ConvertAll(i=>i.Text).ToArray();
        }
    }
}
