import sqlite3, sys, subprocess, threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

NAVY="#07345D"; RED="#BE1E2D"; CREAM="#F7F4F0"; WHITE="#FFFFFF"; TEXT="#1F2933"; GREY="#6B7280"
WARN="#FFF2B2"; CRITICAL="#FFD0D0"; EMPTY="#F5A3A3"

def res(p):
    return Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent))/p

APP=Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent
DB=APP/"filamente.db"
MATS=["PLA","PLA+","PETG","ABS","ASA","TPU","PA / Nylon","PC","PVA","HIPS","PP","Sonstige"]
VERS=["Standard","Matt","Metallic","Silk","Glitter","Transparent","Glow in the Dark","Carbon","Holz","Marmor","Dual Color","Tri Color","Sonstige"]

def con(): return sqlite3.connect(DB)

def cols(c): return {r[1] for r in c.execute("PRAGMA table_info(filamente)").fetchall()}

def init():
    with con() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS filamente(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          hersteller TEXT NOT NULL, farbe TEXT NOT NULL, material TEXT NOT NULL, ausfuehrung TEXT NOT NULL,
          rollen INTEGER NOT NULL DEFAULT 1, gewicht REAL NOT NULL DEFAULT 1000, preis REAL NOT NULL DEFAULT 0,
          lagerplatz TEXT DEFAULT '', notizen TEXT DEFAULT '', mindestbestand INTEGER NOT NULL DEFAULT 2)""")
        existing=cols(c)
        additions=[
          ("gewicht","ALTER TABLE filamente ADD COLUMN gewicht REAL NOT NULL DEFAULT 1000"),
          ("preis","ALTER TABLE filamente ADD COLUMN preis REAL NOT NULL DEFAULT 0"),
          ("lagerplatz","ALTER TABLE filamente ADD COLUMN lagerplatz TEXT DEFAULT ''"),
          ("notizen","ALTER TABLE filamente ADD COLUMN notizen TEXT DEFAULT ''"),
          ("mindestbestand","ALTER TABLE filamente ADD COLUMN mindestbestand INTEGER NOT NULL DEFAULT 2")]
        for name,sql in additions:
            if name not in existing: c.execute(sql)
        c.execute("""CREATE TABLE IF NOT EXISTS drucker(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          hersteller TEXT DEFAULT '',
          modell TEXT DEFAULT '',
          ip TEXT DEFAULT '',
          standort TEXT DEFAULT '',
          notizen TEXT DEFAULT '')""")
        printer_cols={r[1] for r in c.execute("PRAGMA table_info(drucker)").fetchall()}
        if "hersteller" not in printer_cols:
            c.execute("ALTER TABLE drucker ADD COLUMN hersteller TEXT DEFAULT ''")
        if "druckernummer" not in printer_cols:
            c.execute("ALTER TABLE drucker ADD COLUMN druckernummer TEXT DEFAULT ''")
        # Existing printers receive D001, D002 ... once; later numbers stay stable.
        rows=c.execute("SELECT id,druckernummer FROM drucker ORDER BY id").fetchall()
        used={str(r[1]).strip().upper() for r in rows if str(r[1] or "").strip()}
        nxt=1
        for pid,num in rows:
            if str(num or "").strip(): continue
            while f"D{nxt:03d}" in used: nxt+=1
            dn=f"D{nxt:03d}"; used.add(dn)
            c.execute("UPDATE drucker SET druckernummer=? WHERE id=?",(dn,pid))
            nxt+=1

def num(s,label):
    try:
        n=float(str(s).replace(",","."))
        if n<0: raise ValueError
        return n
    except: raise ValueError(f"{label} muss eine gültige positive Zahl sein.")

def refresh_lists():
    with con() as c:
        manufacturers=[r[0] for r in c.execute("SELECT DISTINCT hersteller FROM filamente WHERE TRIM(hersteller)<>'' ORDER BY hersteller COLLATE NOCASE")]
        colors=[r[0] for r in c.execute("SELECT DISTINCT farbe FROM filamente WHERE TRIM(farbe)<>'' ORDER BY farbe COLLATE NOCASE")]
    manufacturer_box["values"]=manufacturers
    color_box["values"]=colors
    manufacturer_filter["values"]=["Alle"]+manufacturers
    color_filter["values"]=["Alle"]+colors

def clear():
    selected.set("")
    defaults={"hersteller":"","farbe":"","material":"PLA","ausfuehrung":"Standard","rollen":"1",
              "gewicht":"1000","preis":"0","lagerplatz":"","notizen":"","mindestbestand":"2"}
    for k,v in defaults.items(): V[k].set(v)
    hersteller_entry.focus()

def save():
    x={k:v.get().strip() for k,v in V.items()}
    if not all(x[k] for k in ("hersteller","farbe","material","ausfuehrung")):
        messagebox.showwarning("Fehlende Angaben","Bitte Hersteller, Farbe, Material und Ausführung ausfüllen."); return
    try:
        rollen=int(x["rollen"]); minimum=int(x["mindestbestand"])
        if rollen<0 or minimum<0: raise ValueError("Rollen und Mindestbestand dürfen nicht negativ sein.")
        gewicht=num(x["gewicht"],"Gewicht"); preis=num(x["preis"],"Preis")
    except ValueError as e:
        messagebox.showerror("Eingabe prüfen",str(e)); return
    d=(x["hersteller"],x["farbe"],x["material"],x["ausfuehrung"],rollen,gewicht,preis,x["lagerplatz"],x["notizen"],minimum)
    with con() as c:
        if selected.get():
            c.execute("""UPDATE filamente SET hersteller=?,farbe=?,material=?,ausfuehrung=?,rollen=?,gewicht=?,
                         preis=?,lagerplatz=?,notizen=?,mindestbestand=? WHERE id=?""",d+(selected.get(),))
        else:
            c.execute("""INSERT INTO filamente(hersteller,farbe,material,ausfuehrung,rollen,gewicht,preis,lagerplatz,notizen,mindestbestand)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",d)
    clear(); refresh_lists(); refresh()

def pick(_=None):
    s=tree.selection()
    if not s:return
    r=tree.item(s[0],"values"); selected.set(r[0])
    keys=["hersteller","farbe","material","ausfuehrung","rollen","gewicht","preis","lagerplatz","notizen","mindestbestand"]
    for k,v in zip(keys,r[1:11]): V[k].set(v)

def delete():
    if not selected.get():
        messagebox.showinfo("Auswahl","Bitte zuerst ein Filament auswählen."); return
    if messagebox.askyesno("Löschen","Ausgewähltes Filament wirklich löschen?"):
        with con() as c: c.execute("DELETE FROM filamente WHERE id=?",(selected.get(),))
        clear(); refresh_lists(); refresh()

def stock_change(sign):
    if not selected.get():
        messagebox.showinfo("Auswahl","Bitte zuerst das Filament in der Tabelle auswählen."); return
    title="Rollen einlagern" if sign>0 else "Rollen entnehmen"
    n=simpledialog.askinteger(title,"Wie viele Rollen?",parent=root,minvalue=1)
    if n is None:return
    with con() as c:
        current=c.execute("SELECT rollen FROM filamente WHERE id=?",(selected.get(),)).fetchone()
        if not current:return
        new=current[0]+sign*n
        if new<0:
            messagebox.showwarning("Bestand","Es sind nicht genügend Rollen auf Lager."); return
        c.execute("UPDATE filamente SET rollen=? WHERE id=?",(new,selected.get()))
    V["rollen"].set(str(new)); refresh()

def refresh(*_):
    for i in tree.get_children(): tree.delete(i)
    q=search.get().lower().strip()
    with con() as c:
        rows=c.execute("""SELECT id,hersteller,farbe,material,ausfuehrung,rollen,gewicht,preis,lagerplatz,notizen,mindestbestand
                          FROM filamente ORDER BY hersteller,material,farbe""").fetchall()
    low=0
    for r in rows:
        if q and q not in " ".join(map(str,r[1:])).lower(): continue
        if fhersteller.get()!="Alle" and fhersteller.get().lower() not in str(r[1]).lower(): continue
        if ffarbe.get()!="Alle" and ffarbe.get().lower() not in str(r[2]).lower(): continue
        if fmat.get()!="Alle" and r[3]!=fmat.get(): continue
        if fver.get()!="Alle" and r[4]!=fver.get(): continue
        rolls=r[5]; minimum=r[10]
        if rolls<=minimum: low+=1
        total_kg=rolls*r[6]/1000; total_val=rolls*r[7]
        tag="normal"
        if rolls==0: tag="empty"
        elif rolls==1 and minimum>=1: tag="critical"
        elif rolls<=minimum: tag="warning"
        tree.insert("","end",values=r+(f"{total_kg:.2f}",f"{total_val:.2f}"),tags=(tag,))
    with con() as c:
        sums=c.execute("SELECT COALESCE(SUM(rollen),0),COALESCE(SUM(rollen*gewicht),0),COALESCE(SUM(rollen*preis),0) FROM filamente").fetchone()
        all_low=c.execute("SELECT COUNT(*) FROM filamente WHERE rollen<=mindestbestand").fetchone()[0]
    status.set(f"{sums[0]} Rollen   |   {sums[1]/1000:.1f} kg   |   Lagerwert {sums[2]:.2f} €")
    warning_status.set("⚠ Kein Filamentbestand" if sums[0]==0 and not rows else (f"⚠ {all_low} Filamente nachbestellen" if all_low else "✓ Bestand ausreichend"))


def next_printer_number():
    with con() as c:
        vals=[str(r[0] or "").strip().upper() for r in c.execute("SELECT druckernummer FROM drucker").fetchall()]
    nums=[]
    for v in vals:
        if v.startswith("D") and v[1:].isdigit(): nums.append(int(v[1:]))
    return f"D{(max(nums)+1 if nums else 1):03d}"

def printer_refresh():
    if "printer_tree" not in globals(): return
    for i in printer_tree.get_children(): printer_tree.delete(i)
    q=printer_search.get().lower().strip()
    with con() as c:
        rows=c.execute("""SELECT id,COALESCE(druckernummer,''),name,COALESCE(hersteller,''),modell,ip,standort,notizen
                          FROM drucker ORDER BY druckernummer COLLATE NOCASE,name COLLATE NOCASE""").fetchall()
    for r in rows:
        if q and q not in " ".join(map(str,r[1:])).lower(): continue
        old=printer_status_cache.get(str(r[0]),("● Noch nicht geprüft","unknown"))
        printer_tree.insert("","end",values=r+(old[0],),tags=(old[1],))

def printer_clear():
    printer_selected.set("")
    for v in PV.values(): v.set("")
    PV["druckernummer"].set(next_printer_number())

def printer_pick(_=None):
    sel=printer_tree.selection()
    if not sel:return
    r=printer_tree.item(sel[0],"values")
    printer_selected.set(r[0])
    for k,v in zip(["druckernummer","name","hersteller","modell","ip","standort","notizen"],r[1:8]): PV[k].set(v)

def printer_save():
    x={k:v.get().strip() for k,v in PV.items()}
    if not x["name"]:
        messagebox.showwarning("Drucker","Bitte einen Druckernamen eingeben."); return
    if not x["druckernummer"]:
        x["druckernummer"]=next_printer_number()
    d=(x["druckernummer"].upper(),x["name"],x["hersteller"],x["modell"],x["ip"],x["standort"],x["notizen"])
    try:
        with con() as c:
            exists=c.execute("SELECT id FROM drucker WHERE UPPER(TRIM(druckernummer))=? AND id<>?",
                             (x["druckernummer"].upper(), int(printer_selected.get() or 0))).fetchone()
            if exists:
                messagebox.showwarning("Drucker","Diese Druckernummer ist bereits vergeben."); return
            if printer_selected.get():
                c.execute("""UPDATE drucker SET druckernummer=?,name=?,hersteller=?,modell=?,ip=?,standort=?,notizen=?
                             WHERE id=?""",d+(printer_selected.get(),))
            else:
                c.execute("""INSERT INTO drucker(druckernummer,name,hersteller,modell,ip,standort,notizen)
                             VALUES(?,?,?,?,?,?,?)""",d)
    except Exception as e:
        messagebox.showerror("Drucker",f"Drucker konnte nicht gespeichert werden:\n{e}"); return
    printer_clear(); printer_refresh()

def printer_delete():
    if not printer_selected.get():
        messagebox.showinfo("Drucker","Bitte zuerst einen Drucker auswählen."); return
    if messagebox.askyesno("Drucker löschen","Ausgewählten Drucker wirklich löschen?"):
        pid=str(printer_selected.get())
        with con() as c: c.execute("DELETE FROM drucker WHERE id=?",(pid,))
        printer_status_cache.pop(pid,None)
        printer_clear(); printer_refresh()

def ping_ip(ip):
    ip=ip.strip()
    if not ip: return ("● Keine IP","unknown")
    try:
        flags=getattr(subprocess,"CREATE_NO_WINDOW",0)
        r=subprocess.run(["ping","-n","1","-w","900",ip],stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,creationflags=flags,timeout=2)
        return ("● Online","online") if r.returncode==0 else ("● Offline","offline")
    except Exception:
        return ("● Offline","offline")

def check_printer_status():
    if printer_checking.get(): return
    printer_checking.set(True)
    printer_status_text.set("Status wird geprüft …")
    with con() as c:
        rows=c.execute("SELECT id,ip FROM drucker").fetchall()
    if not rows:
        printer_checking.set(False); printer_status_text.set("Keine Drucker angelegt"); return

    def worker():
        results={}
        # Each check runs in its own small worker so ~100 printers do not freeze the UI.
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=20) as ex:
            jobs={ex.submit(ping_ip,str(ip or "")):str(pid) for pid,ip in rows}
            for f in as_completed(jobs):
                results[jobs[f]]=f.result()
        def finish():
            printer_status_cache.update(results)
            printer_checking.set(False)
            online=sum(1 for v in results.values() if v[1]=="online")
            offline=sum(1 for v in results.values() if v[1]=="offline")
            unknown=sum(1 for v in results.values() if v[1]=="unknown")
            printer_status_text.set(f"{online} online   |   {offline} offline   |   {unknown} ohne IP")
            printer_refresh()
        root.after(0,finish)
    threading.Thread(target=worker,daemon=True).start()

def schedule_printer_check():
    check_printer_status()
    root.after(60000,schedule_printer_check)


init()
root=tk.Tk(); root.title("Juno modellbau – Lager & Drucker V5.2"); root.geometry("1420x820"); root.minsize(1100,680); root.configure(bg=CREAM)
try: root.iconbitmap(res("assets/juno.ico"))
except: pass

style=ttk.Style()
try: style.theme_use("clam")
except: pass
style.configure("Treeview",rowheight=30,font=("Segoe UI",10),background=WHITE,fieldbackground=WHITE)
style.configure("Treeview.Heading",font=("Segoe UI",10,"bold"),foreground=NAVY)
style.map("Treeview",background=[("selected",NAVY)],foreground=[("selected",WHITE)])

selected=tk.StringVar()
V={k:tk.StringVar() for k in ["hersteller","farbe","material","ausfuehrung","rollen","gewicht","preis","lagerplatz","notizen","mindestbestand"]}
search=tk.StringVar(); fhersteller=tk.StringVar(value="Alle"); ffarbe=tk.StringVar(value="Alle"); fmat=tk.StringVar(value="Alle"); fver=tk.StringVar(value="Alle"); status=tk.StringVar(); warning_status=tk.StringVar()

header=tk.Frame(root,bg=WHITE,height=170); header.pack(fill="x"); header.pack_propagate(False)
try:
    logo_img=tk.PhotoImage(file=res("assets/juno_logo.png")); tk.Label(header,image=logo_img,bg=WHITE).pack(side="left",padx=(28,25),pady=10)
except: pass
titles=tk.Frame(header,bg=WHITE); titles.pack(side="left",pady=38)
tk.Label(titles,text="FILAMENTLAGER",bg=WHITE,fg=NAVY,font=("Segoe UI",24,"bold")).pack(anchor="w")
tk.Label(titles,text="Lager- und Bestandsverwaltung",bg=WHITE,fg=RED,font=("Segoe UI",11,"bold")).pack(anchor="w")
stats=tk.Frame(header,bg=WHITE); stats.pack(side="right",padx=30)
tk.Label(stats,textvariable=status,bg=WHITE,fg=NAVY,font=("Segoe UI",12,"bold")).pack(anchor="e")
tk.Label(stats,textvariable=warning_status,bg=WHITE,fg=RED,font=("Segoe UI",11,"bold")).pack(anchor="e",pady=(5,0))

notebook=ttk.Notebook(root); notebook.pack(fill="both",expand=True,padx=14,pady=(8,14))
main=tk.Frame(notebook,bg=CREAM); notebook.add(main,text="  Filamentlager  ")
printer_page=tk.Frame(notebook,bg=CREAM); notebook.add(printer_page,text="  Drucker  ")
card=tk.Frame(main,bg=WHITE,highlightbackground="#D9DDE2",highlightthickness=1); card.pack(fill="x",padx=8,pady=(8,0))
tk.Label(card,text="Filament-Stammdaten",bg=WHITE,fg=NAVY,font=("Segoe UI",14,"bold")).grid(row=0,column=0,columnspan=5,sticky="w",padx=14,pady=12)

fields=[("Hersteller","hersteller"),("Farbe","farbe"),("Material","material"),("Ausführung","ausfuehrung"),("Anzahl Rollen","rollen"),
        ("Gewicht / Rolle (g)","gewicht"),("Preis / Rolle (€)","preis"),("Mindestbestand","mindestbestand"),("Lagerplatz","lagerplatz"),("Notizen","notizen")]
widgets={}
for i,(lab,k) in enumerate(fields):
    rr=1+(i//5)*2; cc=i%5
    tk.Label(card,text=lab,bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).grid(row=rr,column=cc,sticky="w",padx=10)
    if k=="hersteller": w=ttk.Combobox(card,textvariable=V[k])
    elif k=="farbe": w=ttk.Combobox(card,textvariable=V[k])
    elif k=="material": w=ttk.Combobox(card,textvariable=V[k],values=MATS,state="readonly")
    elif k=="ausfuehrung": w=ttk.Combobox(card,textvariable=V[k],values=VERS,state="readonly")
    elif k in ("rollen","mindestbestand"): w=ttk.Spinbox(card,from_=0,to=9999,textvariable=V[k])
    else: w=ttk.Entry(card,textvariable=V[k])
    w.grid(row=rr+1,column=cc,sticky="ew",padx=10,pady=(2,10),ipady=3); widgets[k]=w
for c in range(5): card.grid_columnconfigure(c,weight=1)
hersteller_entry=widgets["hersteller"]; manufacturer_box=widgets["hersteller"]; color_box=widgets["farbe"]

buttons=tk.Frame(card,bg=WHITE); buttons.grid(row=5,column=0,columnspan=5,sticky="w",padx=10,pady=(0,14))
def B(text,cmd,color):
    return tk.Button(buttons,text=text,command=cmd,bg=color,fg=WHITE,activebackground=color,activeforeground=WHITE,
                     relief="flat",font=("Segoe UI",10,"bold"),padx=15,pady=8,cursor="hand2")
B("Speichern",save,RED).pack(side="left",padx=4)
B("Neues Filament",clear,NAVY).pack(side="left",padx=4)
B("+ Rollen einlagern",lambda:stock_change(1),NAVY).pack(side="left",padx=4)
B("− Rollen entnehmen",lambda:stock_change(-1),RED).pack(side="left",padx=4)
B("Löschen",delete,GREY).pack(side="left",padx=4)

bar=tk.Frame(main,bg=CREAM); bar.pack(fill="x",padx=8,pady=12)
tk.Label(bar,text="Suche",bg=CREAM,fg=NAVY,font=("Segoe UI",10,"bold")).pack(side="left")
ttk.Entry(bar,textvariable=search,width=22).pack(side="left",padx=6)

tk.Label(bar,text="Hersteller",bg=CREAM,fg=NAVY,font=("Segoe UI",10,"bold")).pack(side="left",padx=(10,0))
manufacturer_filter=ttk.Combobox(bar,textvariable=fhersteller,width=16)
manufacturer_filter.pack(side="left",padx=6)

tk.Label(bar,text="Farbe",bg=CREAM,fg=NAVY,font=("Segoe UI",10,"bold")).pack(side="left",padx=(10,0))
color_filter=ttk.Combobox(bar,textvariable=ffarbe,width=14)
color_filter.pack(side="left",padx=6)

tk.Label(bar,text="Material",bg=CREAM,fg=NAVY,font=("Segoe UI",10,"bold")).pack(side="left",padx=(10,0))
ttk.Combobox(bar,textvariable=fmat,values=["Alle"]+MATS,state="readonly",width=12).pack(side="left",padx=6)

tk.Label(bar,text="Ausführung",bg=CREAM,fg=NAVY,font=("Segoe UI",10,"bold")).pack(side="left",padx=(10,0))
ttk.Combobox(bar,textvariable=fver,values=["Alle"]+VERS,state="readonly",width=14).pack(side="left",padx=6)

search.trace_add("write",refresh)
fhersteller.trace_add("write",refresh)
ffarbe.trace_add("write",refresh)
fmat.trace_add("write",refresh)
fver.trace_add("write",refresh)

box=tk.Frame(main,bg=WHITE); box.pack(fill="both",expand=True,padx=8,pady=(0,8))
cols=("id","hersteller","farbe","material","ausfuehrung","rollen","gewicht","preis","lagerplatz","notizen","mindestbestand","gesamtkg","gesamtwert")
heads=["ID","Hersteller","Farbe","Material","Ausführung","Rollen","g/Rolle","€/Rolle","Lagerplatz","Notizen","Minimum","Gesamt kg","Gesamt €"]
tree=ttk.Treeview(box,columns=cols,show="headings")
for c,h in zip(cols,heads): tree.heading(c,text=h)
tree.column("id",width=0,stretch=False)
for c,w in zip(cols[1:],[140,110,80,110,58,70,70,90,130,65,80,80]): tree.column(c,width=w)
tree.tag_configure("warning",background=WARN); tree.tag_configure("critical",background=CRITICAL); tree.tag_configure("empty",background=EMPTY)
ys=ttk.Scrollbar(box,orient="vertical",command=tree.yview); tree.configure(yscrollcommand=ys.set)
tree.pack(side="left",fill="both",expand=True); ys.pack(side="right",fill="y")
tree.bind("<<TreeviewSelect>>",pick)


printer_selected=tk.StringVar()
PV={k:tk.StringVar() for k in ["druckernummer","name","hersteller","modell","ip","standort","notizen"]}
printer_status_cache={}
printer_checking=tk.BooleanVar(value=False)
printer_status_text=tk.StringVar(value="Noch nicht geprüft")
printer_search=tk.StringVar()

pcard=tk.Frame(printer_page,bg=WHITE,highlightbackground="#D9DDE2",highlightthickness=1)
pcard.pack(fill="x",padx=8,pady=(8,0))
tk.Label(pcard,text="Druckerverwaltung",bg=WHITE,fg=NAVY,font=("Segoe UI",14,"bold")).grid(row=0,column=0,columnspan=7,sticky="w",padx=14,pady=12)
pfields=[("Druckernummer","druckernummer"),("Druckername","name"),("Hersteller","hersteller"),("Modell","modell"),
         ("IP-Adresse","ip"),("Standort","standort"),("Notizen","notizen")]
for i,(lab,k) in enumerate(pfields):
    tk.Label(pcard,text=lab,bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).grid(row=1,column=i,sticky="w",padx=10)
    ttk.Entry(pcard,textvariable=PV[k]).grid(row=2,column=i,sticky="ew",padx=10,pady=(2,10),ipady=3)
    pcard.grid_columnconfigure(i,weight=1)
pbuttons=tk.Frame(pcard,bg=WHITE); pbuttons.grid(row=3,column=0,columnspan=7,sticky="w",padx=10,pady=(0,14))
tk.Button(pbuttons,text="Drucker speichern",command=printer_save,bg=RED,fg=WHITE,relief="flat",font=("Segoe UI",10,"bold"),padx=15,pady=8).pack(side="left",padx=4)
tk.Button(pbuttons,text="Neuer Drucker",command=printer_clear,bg=NAVY,fg=WHITE,relief="flat",font=("Segoe UI",10,"bold"),padx=15,pady=8).pack(side="left",padx=4)
tk.Button(pbuttons,text="Drucker löschen",command=printer_delete,bg=GREY,fg=WHITE,relief="flat",font=("Segoe UI",10,"bold"),padx=15,pady=8).pack(side="left",padx=4)
tk.Button(pbuttons,text="Alle Drucker prüfen",command=check_printer_status,bg=NAVY,fg=WHITE,relief="flat",font=("Segoe UI",10,"bold"),padx=15,pady=8).pack(side="left",padx=4)
tk.Label(pbuttons,textvariable=printer_status_text,bg=WHITE,fg=NAVY,font=("Segoe UI",10,"bold")).pack(side="left",padx=14)

pbar=tk.Frame(printer_page,bg=CREAM); pbar.pack(fill="x",padx=8,pady=12)
tk.Label(pbar,text="Drucker suchen",bg=CREAM,fg=NAVY,font=("Segoe UI",10,"bold")).pack(side="left")
ttk.Entry(pbar,textvariable=printer_search,width=32).pack(side="left",padx=8)
tk.Label(pbar,text="Online-Status automatisch alle 60 Sekunden. Filament-Zuordnung folgt als nächster Ausbauschritt.",
         bg=CREAM,fg=GREY,font=("Segoe UI",9)).pack(side="left",padx=12)
printer_search.trace_add("write",lambda *_: printer_refresh())

pbox=tk.Frame(printer_page,bg=WHITE); pbox.pack(fill="both",expand=True,padx=8,pady=(0,8))
pcols=("id","druckernummer","name","hersteller","modell","ip","standort","notizen","status")
pheads=["ID","Nr.","Druckername","Hersteller","Modell","IP-Adresse","Standort","Notizen","Status"]
printer_tree=ttk.Treeview(pbox,columns=pcols,show="headings")
for c,h in zip(pcols,pheads): printer_tree.heading(c,text=h)
printer_tree.column("id",width=0,stretch=False)
for c,w in zip(pcols[1:],[70,150,120,140,135,135,190,95]): printer_tree.column(c,width=w)
printer_tree.tag_configure("online",background="#D9F2DD")
printer_tree.tag_configure("offline",background="#FFD0D0")
printer_tree.tag_configure("unknown",background="#FFF2B2")
pys=ttk.Scrollbar(pbox,orient="vertical",command=printer_tree.yview); printer_tree.configure(yscrollcommand=pys.set)
printer_tree.pack(side="left",fill="both",expand=True); pys.pack(side="right",fill="y")
printer_tree.bind("<<TreeviewSelect>>",printer_pick)

clear(); refresh_lists(); refresh(); printer_clear(); printer_refresh()
root.after(1200,schedule_printer_check)
root.mainloop()

