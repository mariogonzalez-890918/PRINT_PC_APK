package com.jad.print;

import android.content.SharedPreferences;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Alternate routes belong to one pinned server, never to another account/server. */
final class ServerConnection {
    private final SharedPreferences prefs;
    ServerConnection(SharedPreferences prefs){this.prefs=prefs;}
    static final class HttpFailure extends IOException {
        final int status;HttpFailure(int status,String message){super(message);this.status=status;}
    }
    String identity(){
        synchronized(ServerConnection.class){
            if(!prefs.contains("account_origin"))prefs.edit().putString("account_origin",prefs.getString("url","")).commit();
            return prefs.getString("account_origin","");
        }
    }
    private List<String> urls(){
        LinkedHashSet<String> result=new LinkedHashSet<>();result.add(prefs.getString("url",""));
        try{JSONArray values=new JSONArray(prefs.getString("urls","[]"));for(int i=0;i<Math.min(12,values.length());i++)result.add(values.getString(i));}catch(JSONException ignored){}
        result.remove("");return new ArrayList<>(result);
    }
    byte[] request(String path,String auth,String method,byte[] body,String mime,String options) throws Exception {
        identity();
        if(auth.isEmpty()||!auth.equals(prefs.getString("token","")))throw new HttpFailure(403,"Cambió la vinculación del equipo.");
        String primary=prefs.getString("url",""),expected=prefs.getString("server_id","");
        IOException last=null;
        for(String base:urls()){
            try{
                if(!base.equals(primary)){
                    if(expected.isEmpty())continue;
                    JSONObject health=new JSONObject(new String(raw(base+"/api/health","","GET",null,null,null,1500,3000),StandardCharsets.UTF_8));
                    if(!"PRINTER-TAB".equals(health.optString("service"))||!expected.equals(health.optString("server_id")))continue;
                }
                byte[] response=raw(base+path,auth,method,body,mime,options,3500,45000);
                JSONObject result=new JSONObject(new String(response,StandardCharsets.UTF_8));
                synchronized(ServerConnection.class){
                    if(!auth.equals(prefs.getString("token","")))throw new HttpFailure(403,"Cambió la vinculación durante la operación.");
                    SharedPreferences.Editor editor=prefs.edit().putString("url",base);
                    JSONObject connection=result.optJSONObject("_connection");
                    if(connection!=null){
                        String id=connection.optString("server_id");
                        if(!expected.isEmpty()&&!expected.equals(id))throw new HttpFailure(403,"La respuesta pertenece a otro servidor.");
                        if(!id.isEmpty())editor.putString("server_id",id).putString("urls",connection.getJSONArray("urls").toString());
                    }
                    editor.commit();
                }
                return response;
            }catch(HttpFailure error){throw error;}catch(IOException error){last=error;}
        }
        throw new IOException("No se pudo conectar por ninguna dirección LAN/VPN del servidor. "+(last==null?"":last.getMessage()));
    }
    static byte[] raw(String url,String token,String method,byte[] body,String mime,String options,int connectMs,int readMs) throws Exception {
        HttpURLConnection c=(HttpURLConnection)new URL(url).openConnection();c.setInstanceFollowRedirects(false);c.setConnectTimeout(connectMs);c.setReadTimeout(readMs);c.setRequestMethod(method);
        if(!token.isEmpty())c.setRequestProperty("Authorization","Bearer "+token);
        if(options!=null)c.setRequestProperty("X-Print-Options",options);
        try{
            if(body!=null){c.setDoOutput(true);c.setRequestProperty("Content-Type",mime);c.setFixedLengthStreamingMode(body.length);try(OutputStream out=c.getOutputStream()){out.write(body);}}
            int status=c.getResponseCode();InputStream input=status>=200&&status<300?c.getInputStream():c.getErrorStream();
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            if(input!=null)try(InputStream in=input){byte[] chunk=new byte[8192];int n;while((n=in.read(chunk))!=-1){if(bytes.size()+n>2*1024*1024)throw new IOException("Respuesta del servidor demasiado grande.");bytes.write(chunk,0,n);}}
            byte[] response=bytes.toByteArray();
            if(status<200||status>=300){String message="Error HTTP "+status;try{message=new JSONObject(new String(response,StandardCharsets.UTF_8)).optString("error",message);}catch(JSONException ignored){}throw new HttpFailure(status,message);}
            return response;
        }finally{c.disconnect();}
    }
}
