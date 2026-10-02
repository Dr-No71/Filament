import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DB = APP_DIR / "filamente.db"

AUSFUEHRUNGEN = [
    "Standard", "Matt", "Metallic", "Silk", "Glitter", "Transparent",
    "Glow in the Dark", "Carbon", "Holz", "Marmor", "Sonstige"
]

def db():
    return sqlite3.connect(DB)

def init_db():
    with db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS filamente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hersteller TEXT NOT NULL,
            farbe TEXT NOT NULL,
            material TEXT NOT NULL,
            ausfuehrung TEXT NOT NULL,
            rollen INTEGER NOT NULL DEFAULT 1,
            gewicht REAL NOT NULL DEFAULT 1000,
            restgewicht REAL NOT NULL DEFAULT 1000,
            preis REAL NOT NULL DEFAULT 0,
            lagerplatz TEXT DEFAULT '',
            notizen TEXT DEFAULT ''
        )
        """)

def refresh():
    for x in tree.get_children():
        tree.delete(x)
    term = search_var.get().strip().lower()
    with db() as con:
        rows = con.execute("""
            SELECT id, hersteller, farbe, material, ausfuehrung, rollen,
                   gewicht, restgewicht, preis, lagerplatz, notizen
            FROM filamente
            ORDER BY hersteller, material, ausfuehrung, farbe
        """).fetchall()
    for row in rows:
        if term and term not in " ".join(map(str, row[1:])).lower():
            continue
        tree.insert("", "end", values=row)
    update_total()

def update_total():
    with db() as con:
        total = con.execute("SELECT COALESCE(SUM(rollen),0) FROM filamente").fetchone()[0]
        total_weight = con.execute("SELECT COALESCE(SUM(restgewicht),0) FROM filamente").fetchone()[0]
    total_var.set(f"Bestand: {total} Rollen | Restgewicht: {total_weight:.0f} g")

def clear_form():
    selected_id.set("")
    vars_["hersteller"].set("")
    vars_["farbe"].set("")
    vars_["material"].set("")
    vars_["ausfuehrung"].set("Standard")
    vars_["rollen"].set("1")
    vars_["gewicht"].set("1000")
    vars_["restgewicht"].set("1000")
    vars_["preis"].set("0")
    vars_["lagerplatz"].set("")
    vars_["notizen"].set("")
    hersteller.focus()

def num(value, name, minimum=0):
    try:
        n = float(value.replace(",", "."))
        if n < minimum:
            raise ValueError
        return n
    except ValueError:
        raise ValueError(f"{name} muss eine gültige Zahl sein.")

def save():
    h = vars_["hersteller"].get().strip()
    f = vars_["farbe"].get().strip()
    m = vars_["material"].get().strip()
    a = vars_["ausfuehrung"].get().strip()
    lager = vars_["lagerplatz"].get().strip()
    notizen = vars_["notizen"].get().strip()
    if not all([h, f, m, a]):
        messagebox.showwarning("Fehlende Angaben", "Hersteller, Farbe, Material und Ausführung sind Pflichtfelder.")
        return
    try:
        rollen = int(vars_["rollen"].get())
        if rollen < 0: raise ValueError
        gewicht = num(vars_["gewicht"].get(), "Gewicht")
        rest = num(vars_["restgewicht"].get(), "Restgewicht")
        preis = num(vars_["preis"].get(), "Preis")
    except ValueError as e:
        messagebox.showerror("Ungültige Eingabe", str(e))
        return

    with db() as con:
        if selected_id.get():
            con.execute("""UPDATE filamente SET hersteller=?, farbe=?, material=?,
                ausfuehrung=?, rollen=?, gewicht=?, restgewicht=?, preis=?,
                lagerplatz=?, notizen=? WHERE id=?""",
                (h,f,m,a,rollen,gewicht,rest,preis,lager,notizen,selected_id.get()))
        else:
            con.execute("""INSERT INTO filamente
                (hersteller,farbe,material,ausfuehrung,rollen,gewicht,restgewicht,preis,lagerplatz,notizen)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (h,f,m,a,rollen,gewicht,rest,preis,lager,notizen))
    refresh()
    clear_form()

def select_row(_=None):
    sel = tree.selection()
    if not sel: return
    v = tree.item(sel[0], "values")
    selected_id.set(v[0])
    keys = ["hersteller","farbe","material","ausfuehrung","rollen","gewicht","restgewicht","preis","lagerplatz","notizen"]
    for k, val in zip(keys, v[1:]):
        vars_[k].set(val)

def delete():
    sel = tree.selection()
    if not sel:
        messagebox.showinfo("Auswahl", "Bitte zuerst ein Filament auswählen.")
        return
    v = tree.item(sel[0], "values")
    if messagebox.askyesno("Löschen", f"{v[1]} – {v[2]} wirklich löschen?"):
        with db() as con:
            con.execute("DELETE FROM filamente WHERE id=?", (v[0],))
        refresh()
        clear_form()

init_db()
root = tk.Tk()
root.title("Filament Manager")
root.geometry("1250x720")
root.minsize(1000, 600)

selected_id = tk.StringVar()
vars_ = {k: tk.StringVar() for k in [
    "hersteller","farbe","material","ausfuehrung","rollen","gewicht",
    "restgewicht","preis","lagerplatz","notizen"
]}
vars_["ausfuehrung"].set("Standard")
vars_["rollen"].set("1")
vars_["gewicht"].set("1000")
vars_["restgewicht"].set("1000")
vars_["preis"].set("0")
search_var = tk.StringVar()
total_var = tk.StringVar()

top = ttk.Frame(root, padding=12)
top.pack(fill="x")
ttk.Label(top, text="Filament Manager", font=("Segoe UI", 20, "bold")).pack(side="left")
ttk.Label(top, textvariable=total_var, font=("Segoe UI", 11)).pack(side="right")

form = ttk.LabelFrame(root, text="Filamentdaten", padding=10)
form.pack(fill="x", padx=12, pady=(0,10))

fields = [
    ("Hersteller","hersteller",22),("Farbe","farbe",18),("Material","material",16),
    ("Ausführung","ausfuehrung",18),("Rollen","rollen",8),("Gewicht/Rolle (g)","gewicht",12),
    ("Restgewicht gesamt (g)","restgewicht",14),("Preis/Rolle (€)","preis",12),
    ("Lagerplatz","lagerplatz",14),("Notizen","notizen",24)
]
for i,(label,key,width) in enumerate(fields):
    r = 0 if i < 5 else 2
    c = i if i < 5 else i-5
    ttk.Label(form,text=label).grid(row=r,column=c,sticky="w",padx=4,pady=(0,3))
    if key == "ausfuehrung":
        w=ttk.Combobox(form,textvariable=vars_[key],values=AUSFUEHRUNGEN,width=width)
    elif key=="rollen":
        w=ttk.Spinbox(form,from_=0,to=9999,textvariable=vars_[key],width=width)
    else:
        w=ttk.Entry(form,textvariable=vars_[key],width=width)
    w.grid(row=r+1,column=c,sticky="ew",padx=4,pady=(0,8))
    if key=="hersteller": hersteller=w

actions=ttk.Frame(form)
actions.grid(row=4,column=0,columnspan=5,sticky="w")
ttk.Button(actions,text="Speichern / Aktualisieren",command=save).pack(side="left",padx=4)
ttk.Button(actions,text="Neues Filament",command=clear_form).pack(side="left",padx=4)
ttk.Button(actions,text="Ausgewähltes löschen",command=delete).pack(side="left",padx=4)

search=ttk.Frame(root,padding=(12,0,12,8))
search.pack(fill="x")
ttk.Label(search,text="Suche:").pack(side="left")
ttk.Entry(search,textvariable=search_var,width=45).pack(side="left",padx=8)
search_var.trace_add("write",lambda *_: refresh())

frame=ttk.Frame(root,padding=(12,0,12,12))
frame.pack(fill="both",expand=True)
cols=("id","hersteller","farbe","material","ausfuehrung","rollen","gewicht","restgewicht","preis","lagerplatz","notizen")
tree=ttk.Treeview(frame,columns=cols,show="headings",selectmode="browse")
heads=["ID","Hersteller","Farbe","Material","Ausführung","Rollen","Gewicht/Rolle","Restgewicht","Preis/Rolle","Lagerplatz","Notizen"]
widths=[45,150,120,100,130,65,100,100,95,100,180]
for c,h,w in zip(cols,heads,widths):
    tree.heading(c,text=h); tree.column(c,width=w,anchor="center" if c in ("id","rollen") else "w")
ys=ttk.Scrollbar(frame,orient="vertical",command=tree.yview)
tree.configure(yscrollcommand=ys.set)
tree.pack(side="left",fill="both",expand=True); ys.pack(side="right",fill="y")
tree.bind("<<TreeviewSelect>>",select_row)

refresh()
hersteller.focus()
root.mainloop()
