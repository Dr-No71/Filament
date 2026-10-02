import sqlite3, sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

NAVY="#07345D"; RED="#BE1E2D"; CREAM="#F7F4F0"; WHITE="#FFFFFF"; TEXT="#1F2933"

def res(p):
    return Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent))/p

APP=Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent
DB=APP/"filamente.db"
MATS=["PLA","PLA+","PETG","ABS","ASA","TPU","PA / Nylon","PC","PVA","HIPS","PP","Sonstige"]
VERS=["Standard","Matt","Metallic","Silk","Glitter","Transparent","Glow in the Dark","Carbon","Holz","Marmor","Dual Color","Tri Color","Sonstige"]

def con(): return sqlite3.connect(DB)
def init():
    with con() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS filamente(id INTEGER PRIMARY KEY AUTOINCREMENT,
        hersteller TEXT NOT NULL,farbe TEXT NOT NULL,material TEXT NOT NULL,ausfuehrung TEXT NOT NULL,
        rollen INTEGER NOT NULL DEFAULT 1,gewicht REAL NOT NULL DEFAULT 1000,restgewicht REAL NOT NULL DEFAULT 1000,
        preis REAL NOT NULL DEFAULT 0,lagerplatz TEXT DEFAULT '',notizen TEXT DEFAULT '')""")

def number(s,name):
    try:
        n=float(s.replace(",","."))
        if n<0: raise ValueError
        return n
    except: raise ValueError(name+" muss eine gültige Zahl sein.")

def clear():
    selected.set("")
    defaults={"hersteller":"","farbe":"","material":"PLA","ausfuehrung":"Standard","rollen":"1",
              "gewicht":"1000","restgewicht":"1000","preis":"0","lagerplatz":"","notizen":""}
    for k,v in defaults.items(): V[k].set(v)

def save():
    x={k:v.get().strip() for k,v in V.items()}
    if not all(x[k] for k in ("hersteller","farbe","material","ausfuehrung")):
        messagebox.showwarning("Fehlende Angaben","Bitte Hersteller, Farbe, Material und Ausführung ausfüllen."); return
    try:
        rollen=int(x["rollen"]); gewicht=number(x["gewicht"],"Gewicht"); rest=number(x["restgewicht"],"Restgewicht"); preis=number(x["preis"],"Preis")
        if rollen<0: raise ValueError("Rollen muss eine positive Zahl sein.")
    except ValueError as e: messagebox.showerror("Eingabe prüfen",str(e)); return
    d=(x["hersteller"],x["farbe"],x["material"],x["ausfuehrung"],rollen,gewicht,rest,preis,x["lagerplatz"],x["notizen"])
    with con() as c:
        if selected.get():
            c.execute("""UPDATE filamente SET hersteller=?,farbe=?,material=?,ausfuehrung=?,rollen=?,gewicht=?,
            restgewicht=?,preis=?,lagerplatz=?,notizen=? WHERE id=?""",d+(selected.get(),))
        else:
            c.execute("""INSERT INTO filamente(hersteller,farbe,material,ausfuehrung,rollen,gewicht,restgewicht,preis,lagerplatz,notizen)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",d)
    clear(); refresh()

def delete():
    if not selected.get(): messagebox.showinfo("Auswahl","Bitte zuerst ein Filament auswählen."); return
    if messagebox.askyesno("Löschen","Ausgewähltes Filament wirklich löschen?"):
        with con() as c: c.execute("DELETE FROM filamente WHERE id=?",(selected.get(),))
        clear(); refresh()

def pick(_=None):
    s=tree.selection()
    if not s:return
    r=tree.item(s[0],"values"); selected.set(r[0])
    for k,v in zip(["hersteller","farbe","material","ausfuehrung","rollen","gewicht","restgewicht","preis","lagerplatz","notizen"],r[1:]): V[k].set(v)

def refresh(*_):
    for i in tree.get_children(): tree.delete(i)
    q=search.get().lower().strip()
    with con() as c:
        rows=c.execute("SELECT id,hersteller,farbe,material,ausfuehrung,rollen,gewicht,restgewicht,preis,lagerplatz,notizen FROM filamente ORDER BY hersteller,material,farbe").fetchall()
    for r in rows:
        if q and q not in " ".join(map(str,r[1:])).lower(): continue
        if fmat.get()!="Alle" and r[3]!=fmat.get(): continue
        if fver.get()!="Alle" and r[4]!=fver.get(): continue
        tree.insert("","end",values=r)
    with con() as c:
        rolls=c.execute("SELECT COALESCE(SUM(rollen),0) FROM filamente").fetchone()[0]
        grams=c.execute("SELECT COALESCE(SUM(restgewicht),0) FROM filamente").fetchone()[0]
    status.set(f"{rolls} Rollen im Bestand   •   {grams:.0f} g Restgewicht")

init()
root=tk.Tk(); root.title("Juno modellbau – Filamentverwaltung"); root.geometry("1320x780"); root.minsize(1050,650); root.configure(bg=CREAM)
try: root.iconbitmap(res("assets/juno.ico"))
except: pass
style=ttk.Style()
try: style.theme_use("clam")
except: pass
style.configure("Treeview",rowheight=30,font=("Segoe UI",10),background=WHITE,fieldbackground=WHITE)
style.configure("Treeview.Heading",font=("Segoe UI",10,"bold"),foreground=NAVY)
style.map("Treeview",background=[("selected",NAVY)],foreground=[("selected",WHITE)])

selected=tk.StringVar(); V={k:tk.StringVar() for k in ["hersteller","farbe","material","ausfuehrung","rollen","gewicht","restgewicht","preis","lagerplatz","notizen"]}
search=tk.StringVar(); fmat=tk.StringVar(value="Alle"); fver=tk.StringVar(value="Alle"); status=tk.StringVar(); clear()

header=tk.Frame(root,bg=WHITE,height=115); header.pack(fill="x"); header.pack_propagate(False)
try:
    logo=tk.PhotoImage(file=res("assets/juno_logo.png")); tk.Label(header,image=logo,bg=WHITE).pack(side="left",padx=20,pady=8)
except: pass
tb=tk.Frame(header,bg=WHITE); tb.pack(side="left")
tk.Label(tb,text="FILAMENTVERWALTUNG",bg=WHITE,fg=NAVY,font=("Segoe UI",22,"bold")).pack(anchor="w")
tk.Label(tb,text="Juno modellbau",bg=WHITE,fg=RED,font=("Segoe UI",11,"bold")).pack(anchor="w")
tk.Label(header,textvariable=status,bg=WHITE,fg=NAVY,font=("Segoe UI",11,"bold")).pack(side="right",padx=25)

main=tk.Frame(root,bg=CREAM); main.pack(fill="both",expand=True,padx=22,pady=16)
card=tk.Frame(main,bg=WHITE,highlightbackground="#D9DDE2",highlightthickness=1); card.pack(fill="x")
tk.Label(card,text="Filament erfassen / bearbeiten",bg=WHITE,fg=NAVY,font=("Segoe UI",14,"bold")).grid(row=0,column=0,columnspan=5,sticky="w",padx=14,pady=12)
fields=[("Hersteller","hersteller"),("Farbe","farbe"),("Material","material"),("Ausführung","ausfuehrung"),("Anzahl Rollen","rollen"),
("Gewicht / Rolle (g)","gewicht"),("Restgewicht gesamt (g)","restgewicht"),("Preis / Rolle (€)","preis"),("Lagerplatz","lagerplatz"),("Notizen","notizen")]
for i,(lab,k) in enumerate(fields):
    rr=1+(i//5)*2; cc=i%5
    tk.Label(card,text=lab,bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).grid(row=rr,column=cc,sticky="w",padx=10)
    if k=="material": w=ttk.Combobox(card,textvariable=V[k],values=MATS,state="readonly")
    elif k=="ausfuehrung": w=ttk.Combobox(card,textvariable=V[k],values=VERS,state="readonly")
    elif k=="rollen": w=ttk.Spinbox(card,from_=0,to=9999,textvariable=V[k])
    else: w=ttk.Entry(card,textvariable=V[k])
    w.grid(row=rr+1,column=cc,sticky="ew",padx=10,pady=(2,10),ipady=3)
for c in range(5): card.grid_columnconfigure(c,weight=1)

btn=tk.Frame(card,bg=WHITE); btn.grid(row=5,column=0,columnspan=5,sticky="w",padx=10,pady=(0,14))
def B(t,cmd,color):
    return tk.Button(btn,text=t,command=cmd,bg=color,fg=WHITE,activebackground=color,activeforeground=WHITE,relief="flat",font=("Segoe UI",10,"bold"),padx=16,pady=8)
B("Speichern",save,RED).pack(side="left",padx=4); B("Neues Filament",clear,NAVY).pack(side="left",padx=4); B("Ausgewähltes löschen",delete,"#6B7280").pack(side="left",padx=4)

bar=tk.Frame(main,bg=CREAM); bar.pack(fill="x",pady=12)
tk.Label(bar,text="Suche",bg=CREAM,fg=NAVY,font=("Segoe UI",10,"bold")).pack(side="left"); ttk.Entry(bar,textvariable=search,width=32).pack(side="left",padx=8)
tk.Label(bar,text="Material",bg=CREAM,fg=NAVY,font=("Segoe UI",10,"bold")).pack(side="left",padx=(15,0)); ttk.Combobox(bar,textvariable=fmat,values=["Alle"]+MATS,state="readonly",width=15).pack(side="left",padx=8)
tk.Label(bar,text="Ausführung",bg=CREAM,fg=NAVY,font=("Segoe UI",10,"bold")).pack(side="left",padx=(15,0)); ttk.Combobox(bar,textvariable=fver,values=["Alle"]+VERS,state="readonly",width=17).pack(side="left",padx=8)
search.trace_add("write",refresh); fmat.trace_add("write",refresh); fver.trace_add("write",refresh)

tc=tk.Frame(main,bg=WHITE); tc.pack(fill="both",expand=True)
cols=("id","hersteller","farbe","material","ausfuehrung","rollen","gewicht","restgewicht","preis","lagerplatz","notizen")
tree=ttk.Treeview(tc,columns=cols,show="headings")
heads=["ID","Hersteller","Farbe","Material","Ausführung","Rollen","g/Rolle","Restgewicht","€/Rolle","Lagerplatz","Notizen"]
for c,h in zip(cols,heads): tree.heading(c,text=h)
tree.column("id",width=0,stretch=False)
for c,w in zip(cols[1:],[150,120,90,120,65,75,90,75,95,170]): tree.column(c,width=w)
ys=ttk.Scrollbar(tc,orient="vertical",command=tree.yview); tree.configure(yscrollcommand=ys.set)
tree.pack(side="left",fill="both",expand=True); ys.pack(side="right",fill="y"); tree.bind("<<TreeviewSelect>>",pick)
refresh(); root.mainloop()
