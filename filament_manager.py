import sqlite3, sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

NAVY="#07345D"; RED="#BE1E2D"; CREAM="#F7F4F0"; WHITE="#FFFFFF"; TEXT="#1F2933"; GREY="#6B7280"

def res(p):
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / p

APP = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DB = APP / "filamente.db"
MATS=["PLA","PLA+","PETG","ABS","ASA","TPU","PA / Nylon","PC","PVA","HIPS","PP","Sonstige"]
VERS=["Standard","Matt","Metallic","Silk","Glitter","Transparent","Glow in the Dark","Carbon","Holz","Marmor","Dual Color","Tri Color","Sonstige"]

def con(): return sqlite3.connect(DB)

def columns(c):
    return {r[1] for r in c.execute("PRAGMA table_info(filamente)").fetchall()}

def init():
    with con() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS filamente(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hersteller TEXT NOT NULL, farbe TEXT NOT NULL, material TEXT NOT NULL,
        ausfuehrung TEXT NOT NULL, rollen INTEGER NOT NULL DEFAULT 1,
        gewicht REAL NOT NULL DEFAULT 1000, preis REAL NOT NULL DEFAULT 0,
        lagerplatz TEXT DEFAULT '', notizen TEXT DEFAULT '')""")
        # V2 compatibility: old DB may contain restgewicht; it is intentionally ignored in V3.
        cols=columns(c)
        for name, sql in [
            ("gewicht","ALTER TABLE filamente ADD COLUMN gewicht REAL NOT NULL DEFAULT 1000"),
            ("preis","ALTER TABLE filamente ADD COLUMN preis REAL NOT NULL DEFAULT 0"),
            ("lagerplatz","ALTER TABLE filamente ADD COLUMN lagerplatz TEXT DEFAULT ''"),
            ("notizen","ALTER TABLE filamente ADD COLUMN notizen TEXT DEFAULT ''")]:
            if name not in cols: c.execute(sql)

def num(s,label):
    try:
        n=float(str(s).replace(",","."))
        if n<0: raise ValueError
        return n
    except: raise ValueError(f"{label} muss eine gültige positive Zahl sein.")

def clear():
    selected.set("")
    defaults={"hersteller":"","farbe":"","material":"PLA","ausfuehrung":"Standard","rollen":"1",
              "gewicht":"1000","preis":"0","lagerplatz":"","notizen":""}
    for k,v in defaults.items(): V[k].set(v)
    hersteller_entry.focus()

def save():
    x={k:v.get().strip() for k,v in V.items()}
    if not all(x[k] for k in ("hersteller","farbe","material","ausfuehrung")):
        messagebox.showwarning("Fehlende Angaben","Bitte Hersteller, Farbe, Material und Ausführung ausfüllen."); return
    try:
        rollen=int(x["rollen"])
        if rollen<0: raise ValueError("Rollenanzahl darf nicht negativ sein.")
        gewicht=num(x["gewicht"],"Gewicht")
        preis=num(x["preis"],"Preis")
    except ValueError as e:
        messagebox.showerror("Eingabe prüfen",str(e)); return
    d=(x["hersteller"],x["farbe"],x["material"],x["ausfuehrung"],rollen,gewicht,preis,x["lagerplatz"],x["notizen"])
    with con() as c:
        if selected.get():
            c.execute("""UPDATE filamente SET hersteller=?,farbe=?,material=?,ausfuehrung=?,rollen=?,
                         gewicht=?,preis=?,lagerplatz=?,notizen=? WHERE id=?""", d+(selected.get(),))
        else:
            c.execute("""INSERT INTO filamente(hersteller,farbe,material,ausfuehrung,rollen,gewicht,preis,lagerplatz,notizen)
                         VALUES(?,?,?,?,?,?,?,?,?)""", d)
    clear(); refresh()

def pick(_=None):
    s=tree.selection()
    if not s: return
    r=tree.item(s[0],"values")
    selected.set(r[0])
    for k,v in zip(["hersteller","farbe","material","ausfuehrung","rollen","gewicht","preis","lagerplatz","notizen"],r[1:10]):
        V[k].set(v)

def delete():
    if not selected.get():
        messagebox.showinfo("Auswahl","Bitte zuerst ein Filament auswählen."); return
    if messagebox.askyesno("Löschen","Ausgewähltes Filament wirklich löschen?"):
        with con() as c: c.execute("DELETE FROM filamente WHERE id=?",(selected.get(),))
        clear(); refresh()

def stock_change(sign):
    if not selected.get():
        messagebox.showinfo("Auswahl","Bitte zuerst das Filament in der Tabelle auswählen."); return
    title="Rollen einlagern" if sign>0 else "Rollen entnehmen"
    n=simpledialog.askinteger(title,"Wie viele Rollen?",parent=root,minvalue=1)
    if n is None: return
    with con() as c:
        current=c.execute("SELECT rollen FROM filamente WHERE id=?",(selected.get(),)).fetchone()
        if not current: return
        new=current[0]+sign*n
        if new<0:
            messagebox.showwarning("Bestand","Es sind nicht genügend Rollen auf Lager."); return
        c.execute("UPDATE filamente SET rollen=? WHERE id=?",(new,selected.get()))
    V["rollen"].set(str(new)); refresh()

def refresh(*_):
    for i in tree.get_children(): tree.delete(i)
    q=search.get().lower().strip()
    with con() as c:
        rows=c.execute("""SELECT id,hersteller,farbe,material,ausfuehrung,rollen,gewicht,preis,lagerplatz,notizen
                          FROM filamente ORDER BY hersteller,material,farbe""").fetchall()
    for r in rows:
        if q and q not in " ".join(map(str,r[1:])).lower(): continue
        if fmat.get()!="Alle" and r[3]!=fmat.get(): continue
        if fver.get()!="Alle" and r[4]!=fver.get(): continue
        total_kg=(r[5]*r[6])/1000
        total_val=r[5]*r[7]
        tree.insert("","end",values=r+(f"{total_kg:.2f}",f"{total_val:.2f}"))
    with con() as c:
        sums=c.execute("SELECT COALESCE(SUM(rollen),0),COALESCE(SUM(rollen*gewicht),0),COALESCE(SUM(rollen*preis),0) FROM filamente").fetchone()
    status.set(f"{sums[0]} Rollen   |   {sums[1]/1000:.1f} kg   |   Lagerwert {sums[2]:.2f} €")

init()
root=tk.Tk()
root.title("Juno modellbau – Filamentlager")
root.geometry("1380x800"); root.minsize(1080,650); root.configure(bg=CREAM)
try: root.iconbitmap(res("assets/juno.ico"))
except: pass

style=ttk.Style()
try: style.theme_use("clam")
except: pass
style.configure("Treeview",rowheight=30,font=("Segoe UI",10),background=WHITE,fieldbackground=WHITE)
style.configure("Treeview.Heading",font=("Segoe UI",10,"bold"),foreground=NAVY)
style.map("Treeview",background=[("selected",NAVY)],foreground=[("selected",WHITE)])

selected=tk.StringVar()
V={k:tk.StringVar() for k in ["hersteller","farbe","material","ausfuehrung","rollen","gewicht","preis","lagerplatz","notizen"]}
search=tk.StringVar(); fmat=tk.StringVar(value="Alle"); fver=tk.StringVar(value="Alle"); status=tk.StringVar()

# Header with full logo
header=tk.Frame(root,bg=WHITE,height=170)
header.pack(fill="x"); header.pack_propagate(False)
try:
    logo_img=tk.PhotoImage(file=res("assets/juno_logo.png"))
    tk.Label(header,image=logo_img,bg=WHITE).pack(side="left",padx=(28,25),pady=10)
except: pass
titles=tk.Frame(header,bg=WHITE); titles.pack(side="left",pady=40)
tk.Label(titles,text="FILAMENTLAGER",bg=WHITE,fg=NAVY,font=("Segoe UI",24,"bold")).pack(anchor="w")
tk.Label(titles,text="Lager- und Bestandsverwaltung",bg=WHITE,fg=RED,font=("Segoe UI",11,"bold")).pack(anchor="w")
tk.Label(header,textvariable=status,bg=WHITE,fg=NAVY,font=("Segoe UI",12,"bold")).pack(side="right",padx=30)

main=tk.Frame(root,bg=CREAM); main.pack(fill="both",expand=True,padx=22,pady=16)
card=tk.Frame(main,bg=WHITE,highlightbackground="#D9DDE2",highlightthickness=1); card.pack(fill="x")
tk.Label(card,text="Filament-Stammdaten",bg=WHITE,fg=NAVY,font=("Segoe UI",14,"bold")).grid(row=0,column=0,columnspan=5,sticky="w",padx=14,pady=12)

fields=[("Hersteller","hersteller"),("Farbe","farbe"),("Material","material"),("Ausführung","ausfuehrung"),("Anzahl Rollen","rollen"),
        ("Gewicht / Rolle (g)","gewicht"),("Preis / Rolle (€)","preis"),("Lagerplatz","lagerplatz"),("Notizen","notizen")]
for i,(lab,k) in enumerate(fields):
    rr=1+(i//5)*2; cc=i%5
    tk.Label(card,text=lab,bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).grid(row=rr,column=cc,sticky="w",padx=10)
    if k=="material": w=ttk.Combobox(card,textvariable=V[k],values=MATS,state="readonly")
    elif k=="ausfuehrung": w=ttk.Combobox(card,textvariable=V[k],values=VERS,state="readonly")
    elif k=="rollen": w=ttk.Spinbox(card,from_=0,to=9999,textvariable=V[k])
    else: w=ttk.Entry(card,textvariable=V[k])
    w.grid(row=rr+1,column=cc,sticky="ew",padx=10,pady=(2,10),ipady=3)
    if k=="hersteller": hersteller_entry=w
for c in range(5): card.grid_columnconfigure(c,weight=1)

buttons=tk.Frame(card,bg=WHITE); buttons.grid(row=5,column=0,columnspan=5,sticky="w",padx=10,pady=(0,14))
def B(text,cmd,color):
    return tk.Button(buttons,text=text,command=cmd,bg=color,fg=WHITE,activebackground=color,activeforeground=WHITE,
                     relief="flat",font=("Segoe UI",10,"bold"),padx=15,pady=8,cursor="hand2")
B("Speichern",save,RED).pack(side="left",padx=4)
B("Neues Filament",clear,NAVY).pack(side="left",padx=4)
B("+ Rollen einlagern",lambda:stock_change(1),NAVY).pack(side="left",padx=4)
B("− Rollen entnehmen",lambda:stock_change(-1),RED).pack(side="left",padx=4)
B("Löschen",delete,GREY).pack(side="left",padx=4)

bar=tk.Frame(main,bg=CREAM); bar.pack(fill="x",pady=12)
tk.Label(bar,text="Suche",bg=CREAM,fg=NAVY,font=("Segoe UI",10,"bold")).pack(side="left")
ttk.Entry(bar,textvariable=search,width=32).pack(side="left",padx=8)
tk.Label(bar,text="Material",bg=CREAM,fg=NAVY,font=("Segoe UI",10,"bold")).pack(side="left",padx=(15,0))
ttk.Combobox(bar,textvariable=fmat,values=["Alle"]+MATS,state="readonly",width=15).pack(side="left",padx=8)
tk.Label(bar,text="Ausführung",bg=CREAM,fg=NAVY,font=("Segoe UI",10,"bold")).pack(side="left",padx=(15,0))
ttk.Combobox(bar,textvariable=fver,values=["Alle"]+VERS,state="readonly",width=17).pack(side="left",padx=8)
search.trace_add("write",refresh); fmat.trace_add("write",refresh); fver.trace_add("write",refresh)

tablebox=tk.Frame(main,bg=WHITE); tablebox.pack(fill="both",expand=True)
cols=("id","hersteller","farbe","material","ausfuehrung","rollen","gewicht","preis","lagerplatz","notizen","gesamtkg","gesamtwert")
heads=["ID","Hersteller","Farbe","Material","Ausführung","Rollen","g/Rolle","€/Rolle","Lagerplatz","Notizen","Gesamt kg","Gesamt €"]
tree=ttk.Treeview(tablebox,columns=cols,show="headings")
for c,h in zip(cols,heads): tree.heading(c,text=h)
tree.column("id",width=0,stretch=False)
for c,w in zip(cols[1:],[145,115,85,110,60,75,70,90,140,85,85]): tree.column(c,width=w)
ys=ttk.Scrollbar(tablebox,orient="vertical",command=tree.yview); tree.configure(yscrollcommand=ys.set)
tree.pack(side="left",fill="both",expand=True); ys.pack(side="right",fill="y")
tree.bind("<<TreeviewSelect>>",pick)

clear(); refresh(); root.mainloop()
