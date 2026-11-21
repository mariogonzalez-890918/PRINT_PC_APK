package com.jad.print;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.text.InputType;
import android.view.View;
import android.view.ViewGroup;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private SharedPreferences prefs;
    private LinearLayout root,content;
    private TextView notice,fileLabel;
    private Button printButton;
    private Spinner pcSpinner,printerSpinner,scaleSpinner,paperSpinner,colorSpinner;
    private EditText copies;
    private JSONArray allPrinters=new JSONArray();
    private final ArrayList<JSONObject> visiblePrinters=new ArrayList<>();
    private File selectedFile;
    private String selectedName="",selectedMime="";
    private Uri incoming;
    private boolean busy=false;
    private String currentScreen="connect";
    private static final int BLUE=0xff1464c0,INK=0xff19304d,GRAY=0xff60758b;

    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        prefs=getSharedPreferences("jadprint",MODE_PRIVATE);
        if(Intent.ACTION_SEND.equals(getIntent().getAction())) incoming=getIntent().getParcelableExtra(Intent.EXTRA_STREAM);
        buildRoot();
        if(prefs.contains("token")){showPrint();refreshPrinters();}else showConnect();
    }
    @Override protected void onNewIntent(Intent intent){
        super.onNewIntent(intent);setIntent(intent);
        if(Intent.ACTION_SEND.equals(intent.getAction())){
            incoming=intent.getParcelableExtra(Intent.EXTRA_STREAM);
            if(prefs.contains("token")&&!busy){showPrint();if(incoming!=null){Uri uri=incoming;incoming=null;loadFile(uri);}}
        }
    }
    private int dp(int n){return (int)(getResources().getDisplayMetrics().density*n+.5f);}
    private void buildRoot(){
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(0xfff1f5fa);
        root.setPadding(dp(18),dp(12),dp(18),dp(12));
        setContentView(root);
        root.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(dp(18)+insets.getSystemWindowInsetLeft(),dp(12)+insets.getSystemWindowInsetTop(),dp(18)+insets.getSystemWindowInsetRight(),dp(12)+insets.getSystemWindowInsetBottom());return insets;});
        root.addView(text("PRINTER-TAB",28,INK,true));
        root.addView(text("Tus PCs. Tus impresoras.",14,GRAY,false));
        notice=text("",14,INK,false);notice.setPadding(0,dp(12),0,dp(12));notice.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);root.addView(notice);
        ScrollView scroll=new ScrollView(this);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);scroll.addView(content);
        TextView credits=text("Aplicaciones gestionadas, desarrolladas y administradas por Área de TI GMP · sistemas@grupomipan.com",12,GRAY,false);credits.setPadding(0,dp(10),0,0);android.text.util.Linkify.addLinks(credits,android.text.util.Linkify.EMAIL_ADDRESSES);root.addView(credits);
    }
    private TextView text(String value,int size,int color,boolean bold){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(color);if(bold)t.setTypeface(null,Typeface.BOLD);return t;}
    private LinearLayout card(String title){LinearLayout c=new LinearLayout(this);c.setOrientation(LinearLayout.VERTICAL);c.setPadding(dp(18),dp(18),dp(18),dp(18));GradientDrawable bg=new GradientDrawable();bg.setColor(Color.WHITE);bg.setCornerRadius(dp(14));c.setBackground(bg);LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.bottomMargin=dp(16);content.addView(c,lp);TextView h=text(title,20,INK,true);h.setPadding(0,0,0,dp(12));c.addView(h);return c;}
    private Button button(LinearLayout parent,String label,Runnable action){Button b=new Button(this);b.setText(label);b.setAllCaps(false);b.setTextColor(BLUE);b.setMinHeight(dp(52));parent.addView(b,new LinearLayout.LayoutParams(-1,-2));b.setOnClickListener(v->{if(!busy)action.run();});return b;}
    private EditText input(LinearLayout parent,String label,int type){parent.addView(text(label,14,GRAY,false));EditText e=new EditText(this);e.setSingleLine(true);e.setInputType(type);e.setTextSize(17);parent.addView(e,new LinearLayout.LayoutParams(-1,dp(54)));return e;}
    private Spinner spinner(LinearLayout parent,String label,String[] values){parent.addView(text(label,14,GRAY,false));Spinner s=new Spinner(this);parent.addView(s,new LinearLayout.LayoutParams(-1,dp(52)));items(s,Arrays.asList(values));return s;}
    private void items(Spinner s,List<String> values){ArrayAdapter<String> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_item,values);adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);s.setAdapter(adapter);}
    private void say(String message){notice.setText(message);}
    private String base(){return prefs.getString("url","");}
    private interface Work {void run() throws Exception;}
    private void async(Work task){if(busy)return;busy=true;updateButton();worker.execute(()->{try{task.run();}catch(Exception e){runOnUiThread(()->say(friendly(e)));}finally{runOnUiThread(()->{busy=false;updateButton();if(incoming!=null&&"print".equals(currentScreen)){Uri uri=incoming;incoming=null;loadFile(uri);}});}});}
    private String friendly(Exception e){if(e instanceof SocketTimeoutException)return "No hubo confirmación del servidor. Si estabas enviando, reintenta el mismo trabajo; se conservará su identificador.";if(e instanceof ConnectException||e instanceof UnknownHostException)return "No se pudo conectar. Revisa la dirección del servidor, el Wi-Fi y que la consola esté abierta.";return e.getMessage()!=null?e.getMessage():"No se pudo completar la operación.";}
    private byte[] request(String url,String token,String method,byte[] body,String mime,String options) throws Exception{
        HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();c.setConnectTimeout(12000);c.setReadTimeout(45000);c.setInstanceFollowRedirects(false);c.setRequestMethod(method);
        if(!token.isEmpty())c.setRequestProperty("Authorization","Bearer "+token);
        if(options!=null)c.setRequestProperty("X-Print-Options",options);
        try{
            if(body!=null){c.setDoOutput(true);c.setRequestProperty("Content-Type",mime);c.setFixedLengthStreamingMode(body.length);try(OutputStream out=c.getOutputStream()){out.write(body);}}
            int status=c.getResponseCode();InputStream stream=status>=200&&status<300?c.getInputStream():c.getErrorStream();byte[] data=stream==null?new byte[0]:read(stream,2*1024*1024);
            if(status<200||status>=300){String error="Error HTTP "+status;try{error=new JSONObject(new String(data,StandardCharsets.UTF_8)).optString("error",error);}catch(Exception ignored){}throw new IOException(error);}
            return data;
        }finally{c.disconnect();}
    }
    private byte[] read(InputStream input,int max) throws IOException{try(InputStream in=input;ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] chunk=new byte[8192];int n;while((n=in.read(chunk))!=-1){if(out.size()+n>max)throw new IOException("Archivo demasiado grande (máximo 25 MB).");out.write(chunk,0,n);}return out.toByteArray();}}
    private JSONObject api(String path,JSONObject data) throws Exception{return new JSONObject(new String(request(base()+"/api/"+path,prefs.getString("token",""),data==null?"GET":"POST",data==null?null:data.toString().getBytes(StandardCharsets.UTF_8),"application/json",null),StandardCharsets.UTF_8));}

    private void showConnect(){
        currentScreen="connect";content.removeAllViews();printButton=null;
        LinearLayout c=card("Vincular esta tablet");c.addView(text("El administrador genera un código de tablet y decide qué impresoras puedes usar.",15,GRAY,false));
        EditText url=input(c,"Dirección del servidor",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);url.setText(prefs.getString("url","http://"));
        EditText email=input(c,"Correo de la cuenta",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);email.setText(prefs.getString("email",""));
        EditText name=input(c,"Nombre de esta tablet",InputType.TYPE_CLASS_TEXT);name.setText(android.os.Build.MODEL);
        EditText code=input(c,"Código de vinculación",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);
        button(c,"Vincular",()->{
            final String address=url.getText().toString().trim().replaceAll("/+$","");
            final String mail=email.getText().toString().trim(),device=name.getText().toString().trim(),pair=code.getText().toString().trim();
            async(()->{
                URI u=new URI(address);if(!Arrays.asList("http","https").contains(u.getScheme())||u.getHost()==null||u.getRawUserInfo()!=null||!(u.getPath()==null||u.getPath().isEmpty())||u.getQuery()!=null||u.getFragment()!=null)throw new IOException("Usa una dirección como http://192.168.0.10:8765");
                JSONObject b=new JSONObject().put("email",mail).put("name",device).put("code",pair).put("role","tablet");
                JSONObject result=new JSONObject(new String(request(address+"/api/enroll","","POST",b.toString().getBytes(StandardCharsets.UTF_8),"application/json",null),StandardCharsets.UTF_8));
                prefs.edit().putString("url",address).putString("email",mail).putString("token",result.getString("token")).commit();
                runOnUiThread(()->{say("Tablet vinculada. El administrador debe compartirte impresoras.");showPrint();});
                JSONArray list=api("tablet/printers",null).getJSONArray("printers");runOnUiThread(()->applyPrinters(list));
            });
        });
        c.addView(text("Red local o VPN. Si cable y Wi-Fi usan subredes distintas, el router debe permitir llegar a este servidor.",14,GRAY,false));
    }
    private void showPrint(){
        currentScreen="print";content.removeAllViews();
        LinearLayout device=card("1 · Elige dónde imprimir");
        pcSpinner=spinner(device,"Computadora",new String[]{"Cargando..."});printerSpinner=spinner(device,"Impresora",new String[]{"Sin selección"});
        button(device,"Actualizar impresoras",this::refreshPrinters);
        pcSpinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> p){}public void onItemSelected(AdapterView<?> p,View v,int position,long id){filterPrinters();}});
        LinearLayout doc=card("2 · Selecciona el documento");fileLabel=text(selectedFile==null?"PDF, JPG o PNG · hasta 25 MB":selectedName,16,INK,false);doc.addView(fileLabel);
        button(doc,"Elegir archivo",()->{if(prefs.contains("pending")){say("Primero reintenta el envío pendiente o revisa su historial.");return;}Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("*/*");i.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"application/pdf","image/jpeg","image/png"});startActivityForResult(i,10);});
        LinearLayout settings=card("3 · Opciones");copies=input(settings,"Copias (1–20)",InputType.TYPE_CLASS_NUMBER);copies.setText("1");
        scaleSpinner=spinner(settings,"Escala",new String[]{"Ajustar al papel","Tamaño real (tickets / etiquetas)"});
        paperSpinner=spinner(settings,"Papel",new String[]{"Configuración de la impresora","A4","Carta"});
        colorSpinner=spinner(settings,"Color",new String[]{"Color / controlador","Blanco y negro"});
        settings.addView(text("Para rollos de 80/58 mm y etiquetas, configura el tamaño en el controlador de la PC y usa un PDF del tamaño correcto.",14,GRAY,false));
        printButton=button(settings,prefs.contains("pending")?"Reintentar envío pendiente":"Enviar a imprimir",this::sendOrRetry);
        if(prefs.contains("pending"))button(settings,"Descartar envío local",()->new AlertDialog.Builder(this).setTitle("Descartar envío local").setMessage("Esto no cancela un trabajo aceptado por el servidor. Revisa el historial y la cola de Windows antes de imprimirlo de nuevo.").setNegativeButton("Volver",null).setPositiveButton("Ya revisé; descartar",(d,w)->{prefs.edit().remove("pending").commit();new File(getFilesDir(),"pending.bin").delete();showPrint();say("Envío local descartado. Los trabajos aceptados permanecen en el servidor.");}).show());
        if(prefs.contains("pending"))say("Hay un envío sin confirmar. Reintenta el mismo trabajo o consulta el historial antes de enviar otro.");
        LinearLayout more=card("Tu cuenta");more.addView(text(prefs.getString("email","")+"\n"+base(),14,GRAY,false));button(more,"Ver historial",this::showHistory);
        button(more,"Desvincular tablet",()->new AlertDialog.Builder(this).setTitle("Desvincular tablet").setMessage("Necesitarás un código nuevo. Los trabajos aceptados permanecen en el servidor.").setNegativeButton("Cancelar",null).setPositiveButton("Desvincular",(d,w)->{prefs.edit().remove("token").remove("pending").apply();new File(getFilesDir(),"pending.bin").delete();selectedFile=null;allPrinters=new JSONArray();showConnect();}).show());
        applyPrinters(allPrinters);updateButton();
    }
    private void refreshPrinters(){async(()->{JSONArray list=api("tablet/printers",null).getJSONArray("printers");runOnUiThread(()->{applyPrinters(list);say(list.length()==0?"Todavía no tienes impresoras compartidas. Pide al administrador que te asigne permisos.":"Impresoras actualizadas.");});});}
    private void applyPrinters(JSONArray list){allPrinters=list;if(!"print".equals(currentScreen))return;LinkedHashSet<String> names=new LinkedHashSet<>();for(int i=0;i<list.length();i++)names.add(list.optJSONObject(i).optString("pc"));items(pcSpinner,names.isEmpty()?Arrays.asList("Sin PCs compartidas"):new ArrayList<>(names));filterPrinters();}
    private void filterPrinters(){if(pcSpinner==null)return;String pc=String.valueOf(pcSpinner.getSelectedItem());visiblePrinters.clear();ArrayList<String> names=new ArrayList<>();for(int i=0;i<allPrinters.length();i++){JSONObject p=allPrinters.optJSONObject(i);if(pc.equals(p.optString("pc"))){visiblePrinters.add(p);names.add(p.optString("name")+(p.optInt("online")==1?"":" · PC sin conexión"));}}items(printerSpinner,names.isEmpty()?Arrays.asList("Sin impresoras"):names);}
    private void updateButton(){if(printButton!=null){printButton.setEnabled(!busy);printButton.setText(busy?"Procesando...":prefs.contains("pending")?"Reintentar envío pendiente":"Enviar a imprimir");}}
    @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(request==10&&result==RESULT_OK&&data!=null&&data.getData()!=null)loadFile(data.getData());}
    private void loadFile(Uri uri){
        if(prefs.contains("pending")){say("Hay un envío pendiente. Reinténtalo antes de elegir otro archivo.");return;}
        async(()->{
            String name="Documento";try(Cursor cursor=getContentResolver().query(uri,new String[]{OpenableColumns.DISPLAY_NAME},null,null,null)){if(cursor!=null&&cursor.moveToFirst())name=cursor.getString(0);}
            byte[] bytes=read(getContentResolver().openInputStream(uri),25*1024*1024);String mime;
            if(bytes.length>=5&&new String(bytes,0,5,StandardCharsets.US_ASCII).equals("%PDF-"))mime="application/pdf";
            else if(bytes.length>=8&&(bytes[0]&255)==137&&bytes[1]==80&&bytes[2]==78&&bytes[3]==71)mime="image/png";
            else if(bytes.length>=3&&(bytes[0]&255)==255&&(bytes[1]&255)==216&&(bytes[2]&255)==255)mime="image/jpeg";
            else throw new IOException("Selecciona un archivo PDF, JPG o PNG válido.");
            File target=new File(getCacheDir(),"selected.bin");try(FileOutputStream out=new FileOutputStream(target)){out.write(bytes);}
            final String finalName=name,finalMime=mime;runOnUiThread(()->{selectedFile=target;selectedName=finalName;selectedMime=finalMime;if(fileLabel!=null)fileLabel.setText(finalName+" · "+(bytes.length/1024)+" KB");say("Documento listo. Revisa PC, impresora y opciones antes de enviar.");});
        });
    }
    private void sendOrRetry(){
        if(prefs.contains("pending")){async(this::uploadPending);return;}
        if(selectedFile==null){say("Primero selecciona un documento.");return;}
        int position=printerSpinner.getSelectedItemPosition();if(position<0||position>=visiblePrinters.size()){say("Elige una impresora compartida.");return;}
        int count;try{count=Integer.parseInt(copies.getText().toString());if(count<1||count>20)throw new Exception();}catch(Exception e){say("Elige entre 1 y 20 copias.");return;}
        try{
            JSONObject printer=visiblePrinters.get(position);
            JSONObject options=new JSONObject().put("printer",printer.getString("id")).put("copies",count).put("name",selectedName).put("scale",scaleSpinner.getSelectedItemPosition()==0?"fit":"noscale").put("paper",new String[]{"driver","A4","letter"}[paperSpinner.getSelectedItemPosition()]).put("color",colorSpinner.getSelectedItemPosition()==0?"color":"monochrome");
            JSONObject pending=new JSONObject().put("id",UUID.randomUUID().toString()).put("mime",selectedMime).put("options",options);
            File source=selectedFile;
            new AlertDialog.Builder(this).setTitle("Confirmar impresión").setMessage(selectedName+"\n\n"+printer.getString("pc")+" · "+printer.getString("name")+"\nCopias: "+count+(printer.optInt("online")==1?"":"\nLa PC está sin conexión. El trabajo quedará en espera.")).setNegativeButton("Cancelar",null).setPositiveButton("Imprimir",(d,w)->async(()->{
                byte[] bytes=read(new FileInputStream(source),25*1024*1024);
                File target=new File(getFilesDir(),"pending.bin");try(FileOutputStream out=new FileOutputStream(target)){out.write(bytes);out.getFD().sync();}
                if(!prefs.edit().putString("pending",pending.toString()).commit())throw new IOException("No se pudo guardar el envío en la tablet.");
                uploadPending();
            })).show();
        }catch(Exception e){say(friendly(e));}
    }
    private void uploadPending() throws Exception{
        JSONObject pending=new JSONObject(prefs.getString("pending","{}"));
        byte[] file=read(new FileInputStream(new File(getFilesDir(),"pending.bin")),25*1024*1024);
        String encoded=android.util.Base64.encodeToString(pending.getJSONObject("options").toString().getBytes(StandardCharsets.UTF_8),android.util.Base64.NO_WRAP);
        byte[] response=request(base()+"/api/tablet/jobs/"+pending.getString("id"),prefs.getString("token",""),"POST",file,pending.getString("mime"),encoded);
        JSONObject job=new JSONObject(new String(response,StandardCharsets.UTF_8));
        prefs.edit().remove("pending").commit();new File(getFilesDir(),"pending.bin").delete();
        runOnUiThread(()->{selectedFile=null;selectedName="";if(fileLabel!=null)fileLabel.setText("PDF, JPG o PNG · hasta 25 MB");say("Trabajo registrado: "+job.optString("id").substring(0,8)+". Consulta su avance en el historial.");});
    }
    private String status(String value){switch(value){case "queued":return "En espera de la PC";case "claimed":return "Entregado a PC · sin confirmación";case "submitted":return "Enviado a Windows";case "error":return "Error";case "unknown":return "Resultado incierto · revisar PC";default:return value;}}
    private void showHistory(){async(()->{
        JSONArray jobs=api("tablet/jobs",null).getJSONArray("jobs");runOnUiThread(()->{
            currentScreen="history";content.removeAllViews();printButton=null;LinearLayout top=card("Historial de esta tablet");button(top,"Volver a imprimir",()->{showPrint();refreshPrinters();});button(top,"Actualizar historial",this::showHistory);top.addView(text("Enviado a Windows no confirma que el papel salió. Revisa la PC antes de repetir un trabajo sin confirmación.",14,GRAY,false));
            if(jobs.length()==0)top.addView(text("Aún no has enviado documentos.",16,INK,false));
            for(int i=0;i<jobs.length();i++){JSONObject j=jobs.optJSONObject(i);LinearLayout c=card(j.optString("name"));c.addView(text(status(j.optString("status")),17,BLUE,true));c.addView(text(j.optString("message"),14,GRAY,false));c.addView(text(new java.text.SimpleDateFormat("dd/MM/yyyy HH:mm",Locale.getDefault()).format(new Date((long)(j.optDouble("created")*1000)))+" · "+j.optInt("copies")+" copia(s)",14,GRAY,false));}
        });
    });}
    @Override protected void onDestroy(){worker.shutdown();super.onDestroy();}
}
