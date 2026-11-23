package com.jad.print;

import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelFileDescriptor;
import android.print.*;
import android.printservice.PrintJob;
import android.printservice.PrintService;
import android.printservice.PrinterDiscoverySession;
import android.util.AtomicFile;
import android.util.Base64;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

/** Android's spooler owns the UI and supplies the rendered PDF, including selected pages.
 * Network and disk work never run on the spooler callback thread. */
public class PrinterTabPrintService extends PrintService {
    private final Handler main=new Handler(Looper.getMainLooper());
    private final ExecutorService io=Executors.newSingleThreadExecutor();
    private final Set<String> running=new HashSet<>(); // main thread only
    private final Set<String> cancelling=new HashSet<>();
    private boolean connected;
    private static final int MAX=25*1024*1024;

    private SharedPreferences prefs(){return getSharedPreferences("jadprint",MODE_PRIVATE);}
    private String url(){return prefs().getString("url","");}
    private String token(){return prefs().getString("token","");}
    private static String key(String text){return UUID.nameUUIDFromBytes(text.getBytes(StandardCharsets.UTF_8)).toString();}
    private String account(){return key(new ServerConnection(prefs()).identity()+"\n"+token());}
    private String id(PrintJob job){return key("PRINTER-TAB-system-job:"+job.getId().toString());}
    private File folder(){File f=new File(getFilesDir(),"system-print");f.mkdirs();return f;}
    private File file(String id,String suffix){return new File(folder(),id+suffix);}
    private void clean(String id){file(id,".pdf").delete();new AtomicFile(file(id,".json")).delete();prefs().edit().remove("cancel_"+id).apply();}
    private void save(String id,JSONObject meta) throws IOException {
        AtomicFile target=new AtomicFile(file(id,".json"));FileOutputStream out=target.startWrite();
        try{out.write(meta.toString().getBytes(StandardCharsets.UTF_8));target.finishWrite(out);}catch(Exception e){target.failWrite(out);throw new IOException("No se pudo conservar el trabajo.",e);}
    }
    private JSONObject load(String id) throws Exception {
        AtomicFile target=new AtomicFile(file(id,".json"));
        try(InputStream in=target.openRead()){return new JSONObject(new String(read(in,65536),StandardCharsets.UTF_8));}
    }
    private static byte[] read(InputStream in,int limit) throws IOException {
        try(InputStream input=in;ByteArrayOutputStream out=new ByteArrayOutputStream()){
            byte[] buf=new byte[16384];int n;
            while((n=input.read(buf))!=-1){if(out.size()+n>limit)throw new IOException("Documento mayor de 25 MB o respuesta demasiado grande.");out.write(buf,0,n);}return out.toByteArray();
        }
    }
    private static class HttpError extends IOException {
        final int code;HttpError(int code,String message){super(message);this.code=code;}
    }
    private JSONObject request(String base,String auth,String path,byte[] body,String options) throws Exception {
        try{
            byte[] response=new ServerConnection(prefs()).request("/api/client/"+path,auth,body==null?"GET":"POST",body,options==null?"application/json":"application/pdf",options);
            return new JSONObject(new String(response,StandardCharsets.UTF_8));
        }catch(ServerConnection.HttpFailure error){throw new HttpError(error.status,error.getMessage());}
    }
    @Override protected void onConnected(){connected=true;for(PrintJob job:getActivePrintJobs())process(job);}
    @Override protected void onDisconnected(){connected=false;main.removeCallbacksAndMessages(null);}
    @Override public void onDestroy(){connected=false;main.removeCallbacksAndMessages(null);io.shutdownNow();super.onDestroy();}
    @Override protected PrinterDiscoverySession onCreatePrinterDiscoverySession(){return new Discovery();}
    @Override protected void onPrintJobQueued(PrintJob job){process(job);}
    @Override protected void onRequestCancelPrintJob(PrintJob job){
        String id=id(job);
        if(!prefs().edit().putBoolean("cancel_"+id,true).commit()){job.block("No se pudo guardar la cancelación. Reintenta.");return;}
        process(job);
    }
    private void process(PrintJob job){
        if(!connected||job.isCancelled()||job.isCompleted()||job.isFailed())return;
        String id=id(job);if(!running.add(id))return;
        final String base=url(),auth=token(),owner=account();
        final PrintJobInfo info=job.getInfo();
        if(auth.isEmpty()||info.getPrinterId()==null||!info.getPrinterId().getLocalId().startsWith(owner+":")){
            running.remove(id);job.fail("Vincula el dispositivo a PRINTER-TAB y vuelve a seleccionar una impresora de tu cuenta.");return;
        }
        final String printer=info.getPrinterId().getLocalId().substring(owner.length()+1);
        final boolean cancel=prefs().getBoolean("cancel_"+id,false)&&!cancelling.contains(id);
        if(!job.isStarted()&&!job.start()){running.remove(id);return;}
        job.setStatus(cancel?"Cancelando en el servidor…":"Enviando a PRINTER-TAB…");
        // getDocument/getData and all PrintJob API calls belong on the main thread.
        final ParcelFileDescriptor source=cancel||file(id,".json").isFile()?null:job.getDocument().getData();
        io.execute(()->{
            try{
                if(!owner.equals(account()))throw new HttpError(403,"Cambió la vinculación. No se enviará este documento con otra cuenta.");
                if(cancel){
                    JSONObject result=request(base,auth,"jobs/"+id+"/cancel","{}".getBytes(StandardCharsets.UTF_8),null);
                    main.post(()->{running.remove(id);if(!connected)return;
                        if(result.optBoolean("cancelled")){job.cancel();clean(id);cancelling.remove(id);}
                        else {cancelling.add(id);job.setStatus("Ya entregado a la PC: revisa la cola de Windows para detenerlo.");schedule(job,5000);}});
                    return;
                }
                JSONObject meta;
                if(file(id,".json").isFile())meta=load(id);
                else {
                    if(source==null)throw new IOException("Android no entregó el PDF. Reintenta desde el menú Imprimir.");
                    byte[] pdf=read(new ParcelFileDescriptor.AutoCloseInputStream(source),MAX);
                    if(pdf.length<5||!new String(pdf,0,5,StandardCharsets.US_ASCII).equals("%PDF-"))throw new IOException("Android no entregó un documento PDF válido.");
                    PrintAttributes attr=info.getAttributes();PrintAttributes.MediaSize media=attr.getMediaSize();
                    String paper=media!=null&&PrintAttributes.MediaSize.NA_LETTER.getId().equals(media.getId())?"letter":"A4";
                    if(info.getCopies()<1||info.getCopies()>20)throw new HttpError(400,"Selecciona entre 1 y 20 copias.");
                    JSONObject options=new JSONObject().put("printer",printer).put("name",info.getLabel()).put("copies",info.getCopies())
                        .put("scale","fit").put("paper",paper).put("color",attr.getColorMode()==PrintAttributes.COLOR_MODE_MONOCHROME?"monochrome":"color");
                    // fsync PDF first; metadata is the commit marker before any network submission.
                    try(FileOutputStream out=new FileOutputStream(file(id,".pdf"))){out.write(pdf);out.getFD().sync();}
                    meta=new JSONObject().put("account",owner).put("options",options).put("accepted",false);save(id,meta);
                }
                if(!owner.equals(meta.getString("account")))throw new HttpError(403,"La cuenta del trabajo ya no coincide con la vinculación.");
                JSONObject result;
                if(!meta.optBoolean("accepted")){
                    byte[] pdf=read(new FileInputStream(file(id,".pdf")),MAX);
                    String options=Base64.encodeToString(meta.getJSONObject("options").toString().getBytes(StandardCharsets.UTF_8),Base64.NO_WRAP);
                    result=request(base,auth,"jobs/"+id,pdf,options);
                    meta.put("accepted",true);save(id,meta);
                }else result=request(base,auth,"jobs/"+id,null,null);
                final JSONObject state=result;
                main.post(()->{running.remove(id);if(!connected)return;
                    if(prefs().getBoolean("cancel_"+id,false)&&!cancelling.contains(id)){process(job);return;}
                    String status=state.optString("status");
                    if("submitted".equals(status)){job.setStatus("Entregado al controlador Windows; verifica la salida del papel.");job.complete();clean(id);cancelling.remove(id);}
                    else if("cancelled".equals(status)){job.cancel();clean(id);cancelling.remove(id);}
                    else if("error".equals(status)||"unknown".equals(status)){job.fail(state.optString("message","Revisa la PC antes de reenviar."));clean(id);cancelling.remove(id);}
                    else {job.setStatus(cancelling.contains(id)?"No fue posible detenerlo: revisa la cola de Windows.":"queued".equals(status)?"En espera de la PC. Puedes cerrar la aplicación.":"La PC está procesando la impresión…");schedule(job,5000);}
                });
            }catch(Exception e){
                main.post(()->{running.remove(id);if(!connected)return;
                    if(e instanceof HttpError&&((HttpError)e).code>=400&&((HttpError)e).code<500&&((HttpError)e).code!=429){job.fail(e.getMessage());clean(id);}
                    else {job.block("Sin confirmación. Se reintentará el mismo trabajo sin duplicarlo. "+(e.getMessage()==null?"":e.getMessage()));schedule(job,15000);}
                });
            }finally{if(source!=null)try{source.close();}catch(IOException ignored){}}
        });
    }
    private void schedule(PrintJob job,long delay){main.postDelayed(()->process(job),delay);}

    private final class Discovery extends PrinterDiscoverySession {
        private boolean active,destroyed,inFlight;
        private final Runnable refresh=()->fetch();
        @Override public void onStartPrinterDiscovery(List<PrinterId> priority){active=true;fetch();}
        @Override public void onStopPrinterDiscovery(){active=false;main.removeCallbacks(refresh);}
        @Override public void onValidatePrinters(List<PrinterId> printers){fetch();}
        @Override public void onStartPrinterStateTracking(PrinterId printer){fetch();}
        @Override public void onStopPrinterStateTracking(PrinterId printer){}
        @Override public void onDestroy(){destroyed=true;active=false;main.removeCallbacks(refresh);}
        private void fetch(){
            if(destroyed||inFlight)return;
            if(token().isEmpty()){List<PrinterId> old=new ArrayList<>();for(PrinterInfo p:getPrinters())old.add(p.getId());removePrinters(old);return;}
            inFlight=true;final String base=url(),auth=token(),owner=account();
            io.execute(()->{
                try{
                    JSONArray found=request(base,auth,"printers",null,null).getJSONArray("printers");
                    main.post(()->{
                        inFlight=false;if(destroyed)return;
                        if(!owner.equals(account())){fetch();return;}
                        List<PrinterInfo> printers=new ArrayList<>();Set<PrinterId> ids=new HashSet<>();
                        for(int i=0;i<found.length();i++){
                            JSONObject p=found.optJSONObject(i);if(p==null)continue;
                            PrinterId id=generatePrinterId(owner+":"+p.optString("id"));ids.add(id);
                            PrinterCapabilitiesInfo caps=new PrinterCapabilitiesInfo.Builder(id)
                                .addMediaSize(PrintAttributes.MediaSize.ISO_A4,true).addMediaSize(PrintAttributes.MediaSize.NA_LETTER,false)
                                .addResolution(new PrintAttributes.Resolution("300","300 dpi",300,300),true)
                                .setMinMargins(new PrintAttributes.Margins(200,200,200,200))
                                .setColorModes(PrintAttributes.COLOR_MODE_COLOR|PrintAttributes.COLOR_MODE_MONOCHROME,PrintAttributes.COLOR_MODE_COLOR)
                                .setDuplexModes(PrintAttributes.DUPLEX_MODE_NONE,PrintAttributes.DUPLEX_MODE_NONE).build();
                            printers.add(new PrinterInfo.Builder(id,p.optString("pc")+" · "+p.optString("name"),PrinterInfo.STATUS_IDLE)
                                .setDescription(p.optInt("online")==1?"PRINTER-TAB · controlador Windows":"PRINTER-TAB · PC sin conexión; envío en espera")
                                .setCapabilities(caps).build());
                        }
                        List<PrinterId> removed=new ArrayList<>();for(PrinterInfo p:getPrinters())if(!ids.contains(p.getId()))removed.add(p.getId());
                        removePrinters(removed);addPrinters(printers);again();
                    });
                }catch(Exception e){main.post(()->{inFlight=false;if(destroyed)return;
                    List<PrinterInfo> unavailable=new ArrayList<>();for(PrinterInfo p:getPrinters())unavailable.add(new PrinterInfo.Builder(p).setStatus(PrinterInfo.STATUS_UNAVAILABLE).setDescription("Sin conexión al servidor PRINTER-TAB").build());addPrinters(unavailable);again();});}
            });
        }
        private void again(){main.removeCallbacks(refresh);if(active&&!destroyed)main.postDelayed(refresh,10000);}
    }
}
