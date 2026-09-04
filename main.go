package main

import (
 "crypto/sha1"
 "embed"
 "encoding/base64"
 "encoding/json"
 "fmt"
 "log"
 "net"
 "net/http"
 "os"
 "runtime"
 "strconv"
 "sync/atomic"
 "time"
)

//go:embed web/index.html
var files embed.FS

var started = time.Now().UTC()
var instance = strconv.FormatInt(time.Now().UnixNano(), 36)
var totalRequests uint64
var wsOpened uint64
var wsActive int64
var wsClosed uint64

func port() string { if x := os.Getenv("PORT"); x != "" { return x }; return "8080" }
func jsonReply(w http.ResponseWriter, x any) { w.Header().Set("Content-Type", "application/json; charset=utf-8"); w.Header().Set("Cache-Control", "no-store"); json.NewEncoder(w).Encode(x) }
func common(w http.ResponseWriter, r *http.Request, next http.HandlerFunc) { atomic.AddUint64(&totalRequests, 1); w.Header().Set("X-Probe-Instance", instance); w.Header().Set("X-Probe-Version", "v0.1.0"); next(w,r) }
func main() {
 mux:=http.NewServeMux()
 wrap:=func(h http.HandlerFunc) http.HandlerFunc{return func(w http.ResponseWriter,r *http.Request){common(w,r,h)}}
 mux.HandleFunc("/",wrap(home)); mux.HandleFunc("/healthz",wrap(health)); mux.HandleFunc("/readyz",wrap(ready)); mux.HandleFunc("/api/report",wrap(report)); mux.HandleFunc("/api/headers",wrap(headers)); mux.HandleFunc("/ws",wrap(ws))
 log.Printf("probe listening on :%s",port())
 log.Fatal(http.ListenAndServe(":"+port(),mux))
}
func home(w http.ResponseWriter,r *http.Request){if r.URL.Path!="/"{http.NotFound(w,r);return}; b,_:=files.ReadFile("web/index.html");w.Header().Set("Content-Type","text/html; charset=utf-8");w.Write(b)}
func health(w http.ResponseWriter,r *http.Request){jsonReply(w,map[string]any{"ok":true,"message":"容器正常运行","time":time.Now().UTC().Format(time.RFC3339)})}
func ready(w http.ResponseWriter,r *http.Request){jsonReply(w,map[string]any{"ready":true,"port":port(),"uptime_seconds":int(time.Since(started).Seconds())})}
func report(w http.ResponseWriter,r *http.Request){var m runtime.MemStats;runtime.ReadMemStats(&m);jsonReply(w,map[string]any{"version":"v0.1.0","instance_id":instance,"started_at":started.Format(time.RFC3339),"uptime_seconds":int(time.Since(started).Seconds()),"listen_port":port(),"requests_total":atomic.LoadUint64(&totalRequests),"runtime":map[string]any{"go_version":runtime.Version(),"arch":runtime.GOARCH,"goroutines":runtime.NumGoroutine(),"heap_alloc_mib":float64(m.HeapAlloc)/1048576,"heap_sys_mib":float64(m.HeapSys)/1048576,"active_websockets":atomic.LoadInt64(&wsActive),"websockets_opened":atomic.LoadUint64(&wsOpened),"websockets_closed":atomic.LoadUint64(&wsClosed)})}
func headers(w http.ResponseWriter,r *http.Request){h:=map[string]string{};for _,k:=range []string{"Host","User-Agent","Accept","Connection","Upgrade","Sec-WebSocket-Version","X-Forwarded-For","X-Forwarded-Proto","X-Real-Ip","Cf-Connecting-Ip","Cf-Ray","Cf-Ipcountry"}{if v:=r.Header.Get(k);v!=""{h[k]=v}};jsonReply(w,map[string]any{"method":r.Method,"path":r.URL.Path,"query":r.URL.RawQuery,"protocol":r.Proto,"host":r.Host,"remote_addr":r.RemoteAddr,"headers":h})}
func ws(w http.ResponseWriter,r *http.Request){if r.Header.Get("Upgrade")!="websocket"{http.Error(w,"请使用 WebSocket 访问 /ws",400);return};key:=r.Header.Get("Sec-WebSocket-Key");if key==""{http.Error(w,"缺少 WebSocket Key",400);return};hj,ok:=w.(http.Hijacker);if !ok{http.Error(w,"当前环境不支持 WebSocket",500);return};c,b,err:=hj.Hijack();if err!=nil{return};defer c.Close();sum:=sha1.Sum([]byte(key+"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"));fmt.Fprintf(b,"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\nX-Probe-Instance: %s\r\n\r\n",base64.StdEncoding.EncodeToString(sum[:] ),instance);b.Flush();atomic.AddUint64(&wsOpened,1);atomic.AddInt64(&wsActive,1);defer func(){atomic.AddInt64(&wsActive,-1);atomic.AddUint64(&wsClosed,1)}();c.SetDeadline(time.Now().Add(15*time.Minute));for{op,data,err:=readFrame(c);if err!=nil{return};if op==8{writeFrame(c,8,data);return};if op==9{writeFrame(c,10,data);continue};if op==1||op==2{writeFrame(c,op,data)}}}
func readFull(c net.Conn,b []byte)error{for n:=0;n<len(b);{x,e:=c.Read(b[n:]);if e!=nil{return e};n+=x};return nil}
func readFrame(c net.Conn)(byte,[]byte,error){h:=make([]byte,2);if e:=readFull(c,h);e!=nil{return 0,nil,e};op:=h[0]&15;n:=int64(h[1]&127);if n==126{b:=make([]byte,2);if e:=readFull(c,b);e!=nil{return 0,nil,e};n=int64(b[0])<<8|int64(b[1])};if n==127{b:=make([]byte,8);if e:=readFull(c,b);e!=nil{return 0,nil,e};n=0;for _,v:=range b{n=n<<8|int64(v)}};if n>1048576{return 0,nil,fmt.Errorf("message too large")};mask:=make([]byte,4);if e:=readFull(c,mask);e!=nil{return 0,nil,e};d:=make([]byte,n);if e:=readFull(c,d);e!=nil{return 0,nil,e};for i:=range d{d[i]^=mask[i%4]};return op,d,nil}
func writeFrame(c net.Conn,op byte,d []byte)error{n:=len(d);h:=[]byte{128|op};if n<126{h=append(h,byte(n))}else{h=append(h,126,byte(n>>8),byte(n))};if _,e:=c.Write(h);e!=nil{return e};_,e:=c.Write(d);return e}
