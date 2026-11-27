import java.nio.file.*; import java.util.*;
import lf.sandbox.time.formatcanary.FormatCanaryService;
/** Audit reproducer req-825 (commit e7bac83). Inputs come from repro_args.json, decoded by python into one arg file per line (NUL-free base64). Prints JSON lines. */
public class FormatCanaryAuditReproducer {
  static String q(String s){ if(s==null) return "null"; StringBuilder b=new StringBuilder("\""); for(char c: s.toCharArray()){ if(c=='"'||c=='\\') b.append('\\').append(c); else if(c<0x20||c>0x7e) b.append(String.format("\\u%04x",(int)c)); else b.append(c);} return b.append('"').toString(); }
  public static void main(String[] a) throws Exception {
    List<String> lines = Files.readAllLines(Paths.get(a[0])); String expected=a[1]; int iters=Integer.parseInt(a[2]);
    FormatCanaryService svc = new FormatCanaryService();
    for(String l: lines){ String[] p=l.split(" ",2); String kind=p[0]; String in = p[1].equals("NULL")?null:new String(Base64.getDecoder().decode(p[1]),"UTF-8");
      String outcome, msg=null, ret=null; boolean reflects=false;
      long s=System.nanoTime();
      try { ret=svc.validate(in); outcome="ACCEPTED"; } catch(IllegalArgumentException e){ outcome="IAE"; msg=e.getMessage(); reflects = in!=null && !in.isEmpty() && msg!=null && msg.contains(in); } catch(Throwable t){ outcome="OTHER:"+t.getClass().getName(); }
      long ns=System.nanoTime()-s;
      boolean pass = kind.equals("accept") ? outcome.equals("ACCEPTED") && in.equals(ret) : outcome.equals("IAE") && expected.equals(msg) && !reflects;
      System.out.println("{\"kind\":\""+kind+"\",\"input\":"+q(in)+",\"outcome\":\""+outcome+"\",\"message\":"+q(msg)+",\"returned\":"+q(ret)+",\"message_reflects_input\":"+reflects+",\"first_call_ns\":"+ns+",\"pass\":"+pass+"}");
    }
    long s=System.nanoTime(); for(int i=0;i<iters;i++){ try{svc.validate(i%2==0?"canary-ok":"x");}catch(IllegalArgumentException e){} }
    System.out.printf(Locale.ROOT,"{\"kind\":\"timing\",\"iterations\":%d,\"avg_ns\":%.1f}%n",iters,(System.nanoTime()-s)/(double)iters);
  }
}
