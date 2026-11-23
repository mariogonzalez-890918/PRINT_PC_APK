package com.jad.print;

import android.content.SharedPreferences;
import com.sun.net.httpserver.*;
import java.lang.reflect.Proxy;
import java.net.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.json.*;

/** JVM test of the same routing class shipped in Android; no phone or real printing. */
public class ServerConnectionTest {
    static void check(boolean test,String message){if(!test)throw new AssertionError(message);}
    static SharedPreferences preferences(Map<String,Object> values){
        return (SharedPreferences)Proxy.newProxyInstance(SharedPreferences.class.getClassLoader(),new Class[]{SharedPreferences.class},(p,m,a)->{
            switch(m.getName()){
                case "contains":return values.containsKey(a[0]);
                case "getString":return values.getOrDefault(a[0].toString(),a[1]);
                case "edit":
                    Map<String,Object> changes=new HashMap<>();
                    return Proxy.newProxyInstance(SharedPreferences.Editor.class.getClassLoader(),new Class[]{SharedPreferences.Editor.class},(e,em,ea)->{
                        if(em.getName().equals("putString")){changes.put(ea[0].toString(),ea[1]);return e;}
                        if(em.getName().equals("commit")||em.getName().equals("apply")){values.putAll(changes);return em.getName().equals("commit")?true:null;}
                        throw new UnsupportedOperationException(em.getName());
                    });
                default:throw new UnsupportedOperationException(m.getName());
            }
        });
    }
    static void reply(HttpExchange e,int status,String json)throws IOException{
        byte[] body=json.getBytes(StandardCharsets.UTF_8);e.sendResponseHeaders(status,body.length);try(OutputStream out=e.getResponseBody()){out.write(body);}
    }
    public static void main(String[] args)throws Exception{
        HttpServer first=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        HttpServer second=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        HttpServer wrong=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        String primary="http://127.0.0.1:"+first.getAddress().getPort(),alternate="http://127.0.0.1:"+second.getAddress().getPort(),stranger="http://127.0.0.1:"+wrong.getAddress().getPort();
        Set<String> jobs=new HashSet<>();AtomicBoolean lost=new AtomicBoolean(false);List<String> wrongAuth=new ArrayList<>();
        final String printersJson=new JSONObject().put("printers",new JSONArray()).put("_connection",new JSONObject().put("server_id","same-server").put("urls",new JSONArray(Arrays.asList(primary,alternate)))).toString();
        HttpHandler shared=e->{
            String path=e.getRequestURI().getPath();
            if(path.equals("/api/health")){reply(e,200,"{\"service\":\"PRINTER-TAB\",\"server_id\":\"same-server\"}");return;}
            e.getRequestBody().readAllBytes();
            if(path.equals("/api/client/denied")){reply(e,403,"{\"error\":\"disabled\"}");return;}
            if(path.startsWith("/api/client/jobs/")){
                jobs.add(path);
                if(e.getLocalAddress().getPort()==first.getAddress().getPort()&&!lost.getAndSet(true)){e.close();return;}
                reply(e,201,"{\"status\":\"queued\"}");return;
            }
            reply(e,200,printersJson);
        };
        first.createContext("/",shared);second.createContext("/",shared);
        wrong.createContext("/",e->{wrongAuth.add(e.getRequestHeaders().getFirst("Authorization"));reply(e,200,"{\"service\":\"PRINTER-TAB\",\"server_id\":\"different-server\"}");});
        first.start();second.start();wrong.start();
        try{
            Map<String,Object> values=new HashMap<>();values.put("url",primary);values.put("token","synthetic-token");values.put("server_id","same-server");values.put("urls",new JSONArray(Arrays.asList(primary,alternate)).toString());
            ServerConnection connection=new ServerConnection(preferences(values));String identity=connection.identity();
            String job="/api/client/jobs/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
            connection.request(job,"synthetic-token","POST","%PDF-fixture".getBytes(StandardCharsets.UTF_8),"application/pdf","e30=");
            check(lost.get()&&jobs.size()==1,"Lost upload response must keep the same job id");
            check(values.get("url").equals(alternate),"Should move to alternate route");check(connection.identity().equals(identity),"Changing network must not change print account identity");
            values.put("url","http://127.0.0.1:1");values.put("urls",new JSONArray(Arrays.asList(stranger,alternate)).toString());
            connection.request("/api/client/printers","synthetic-token","GET",null,"application/json",null);
            check(wrongAuth.size()==1&&wrongAuth.get(0)==null,"Different server must not receive credentials");
            check(new JSONArray(values.get("urls").toString()).length()==2,"Client should learn advertised routes");
            try{connection.request("/api/client/denied","synthetic-token","GET",null,"application/json",null);throw new AssertionError("HTTP 403 must not be retried");}catch(ServerConnection.HttpFailure e){check(e.status==403,"Expected 403");}
            try{connection.request("/api/client/printers","old-token","GET",null,"application/json",null);throw new AssertionError("Account change must reject old token");}catch(ServerConnection.HttpFailure e){check(e.status==403,"Expected changed-account rejection");}
            System.out.println("ANDROID ROUTING: upload retry, stable identity, verified fallback, learned routes and revoked token OK");
        }finally{first.stop(0);second.stop(0);wrong.stop(0);}
    }
}
