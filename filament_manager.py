import sqlite3, sys, subprocess, threading, os, shutil
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

NAVY="#07345D"; RED="#BE1E2D"; CREAM="#F7F4F0"; WHITE="#FFFFFF"; TEXT="#1F2933"; GREY="#6B7280"
WARN="#FFF2B2"; CRITICAL="#FFD0D0"; EMPTY="#F5A3A3"

def res(p):
    return Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent))/p

APP=Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent

# Die Datenbank liegt dauerhaft im Windows-Benutzerprofil. Dadurch bleiben
# Filamente, Drucker und Slot-Belegungen auch nach einem EXE-Update erhalten.
if getattr(sys,"frozen",False) and sys.platform.startswith("win"):
    DATA_DIR=Path(os.environ.get("LOCALAPPDATA", APP))/"JunoModellbau"
else:
    DATA_DIR=APP
DATA_DIR.mkdir(parents=True,exist_ok=True)
DB=DATA_DIR/"filamente.db"

# Vorhandene Datenbank aus älteren Versionen einmalig übernehmen.
LEGACY_DB=APP/"filamente.db"
if DB != LEGACY_DB and not DB.exists() and LEGACY_DB.exists():
    try:
        shutil.copy2(LEGACY_DB,DB)
    except Exception:
        DB=LEGACY_DB
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
        # Datenbank-Migration: ältere Versionen besitzen die Spalte noch nicht.
        drucker_cols = {row[1] for row in c.execute("PRAGMA table_info(drucker)").fetchall()}
        if "filamentplaetze" not in drucker_cols:
            c.execute("ALTER TABLE drucker ADD COLUMN filamentplaetze INTEGER NOT NULL DEFAULT 1")

        # V5.5 migration: slot table for variable filament positions per printer.
        c.execute("""CREATE TABLE IF NOT EXISTS drucker_slots(
          drucker_id INTEGER NOT NULL,
          slot_nr INTEGER NOT NULL,
          filament_id INTEGER,
          PRIMARY KEY (drucker_id, slot_nr),
          FOREIGN KEY (drucker_id) REFERENCES drucker(id) ON DELETE CASCADE,
          FOREIGN KEY (filament_id) REFERENCES filamente(id) ON DELETE SET NULL)""")

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
        printer_tree.insert("","end",values=r+(printer_color_summary(r[0]),old[0]),tags=(old[1],))

def refresh_printer_manufacturers():
    if "printer_manufacturer_box" not in globals(): return
    with con() as c:
        vals=[r[0] for r in c.execute("""SELECT DISTINCT TRIM(hersteller) FROM drucker
                                        WHERE TRIM(COALESCE(hersteller,''))<>''
                                        ORDER BY hersteller COLLATE NOCASE""").fetchall()]
    printer_manufacturer_box["values"]=vals


def ensure_printer_slots(pid, count):
    count=min(10,max(1,int(count or 1)))
    with con() as c:
        existing={r[0] for r in c.execute("SELECT slot_nr FROM drucker_slots WHERE drucker_id=?",(pid,)).fetchall()}
        for n in range(1,count+1):
            if n not in existing:
                c.execute("INSERT OR IGNORE INTO drucker_slots(drucker_id,slot_nr,filament_id) VALUES(?,?,NULL)",(pid,n))
        c.execute("DELETE FROM drucker_slots WHERE drucker_id=? AND slot_nr>?",(pid,count))

def refresh_slot_filament_choices():
    if "slot_filament_box" not in globals(): return
    with con() as c:
        rows=c.execute("""SELECT id,hersteller,farbe,material,ausfuehrung FROM filamente
                          ORDER BY hersteller,farbe,material,ausfuehrung""").fetchall()
    global slot_filament_map
    slot_filament_map={}
    vals=["— frei —"]
    for r in rows:
        label=f"{r[1]} | {r[2]} | {r[3]} | {r[4]}"
        vals.append(label); slot_filament_map[label]=r[0]
    slot_filament_box["values"]=vals

def printer_color_summary(pid):
    # Die Farbanzeige erfolgt als echte farbige Slot-Kästchen über der Treeview-Zelle.
    return ""

def filament_display_color(name):
    """Filament-Farbnamen robust in Anzeigefarben umsetzen."""
    raw = str(name or "").strip().lower()
    if not raw:
        return "#E5E7EB"

    # Schreibweisen vereinheitlichen: Hellgrün == Hell Grün, dunkel-blau == Dunkel Blau.
    text = raw.replace("-", " ").replace("_", " ")
    text = " ".join(text.split())

    # Häufige zusammengesetzte Farben zuerst prüfen.
    special = {
        "hell grün":"#81C784", "hellgrün":"#81C784",
        "dunkel grün":"#1B5E20", "dunkelgrün":"#1B5E20",
        "hell blau":"#64B5F6", "hellblau":"#64B5F6",
        "dunkel blau":"#0D47A1", "dunkelblau":"#0D47A1",
        "hell rot":"#EF9A9A", "hellrot":"#EF9A9A",
        "dunkel rot":"#B71C1C", "dunkelrot":"#B71C1C",
        "hell grau":"#D6D6D6", "hellgrau":"#D6D6D6",
        "dunkel grau":"#616161", "dunkelgrau":"#616161",
        "hell pink":"#F8BBD0", "hellpink":"#F8BBD0",
        "dunkel pink":"#C2185B", "dunkelpink":"#C2185B",
        "hell lila":"#CE93D8", "helllila":"#CE93D8",
        "dunkel lila":"#6A1B9A", "dunkellila":"#6A1B9A",
        "hell orange":"#FFCC80", "hellorange":"#FFCC80",
        "dunkel orange":"#E65100", "dunkelorange":"#E65100",
        "hell gelb":"#FFF59D", "hellgelb":"#FFF59D",
        "dunkel gelb":"#F9A825", "dunkelgelb":"#F9A825",
        "hell braun":"#BCAAA4", "hellbraun":"#BCAAA4",
        "dunkel braun":"#4E342E", "dunkelbraun":"#4E342E",
        "hell türkis":"#80CBC4", "helltürkis":"#80CBC4",
        "dunkel türkis":"#00695C", "dunkeltürkis":"#00695C",
    }
    compact = text.replace(" ", "")
    if text in special:
        return special[text]
    if compact in special:
        return special[compact]

    # Grundfarben. Zusätze wie "Silk", "Matt", "Metallic", "Neon" usw.
    # stören die Erkennung nicht mehr.
    bases = [
        (("schwarz","black"), "#111111"),
        (("weiß","weiss","white"), "#FFFFFF"),
        (("grau","grey","gray"), "#9E9E9E"),
        (("silber","silver"), "#C0C0C0"),
        (("gold","golden"), "#D4AF37"),
        (("rot","red"), "#E53935"),
        (("blau","blue"), "#1E88E5"),
        (("grün","gruen","green"), "#43A047"),
        (("gelb","yellow"), "#FDD835"),
        (("orange",), "#FB8C00"),
        (("braun","brown"), "#795548"),
        (("lila","violett","purple","violet"), "#8E24AA"),
        (("pink","rosa"), "#EC407A"),
        (("türkis","tuerkis","turkis","cyan"), "#26A69A"),
        (("beige","creme","cream"), "#D7CCC8"),
    ]

    # Hell/Dunkel auch bei zusätzlichen Wörtern erkennen,
    # z.B. "PLA Hell Grün Silk".
    is_light = ("hell" in text) or ("light" in text)
    is_dark = ("dunkel" in text) or ("dark" in text)

    light_map = {
        "#111111":"#757575", "#9E9E9E":"#D6D6D6", "#E53935":"#EF9A9A",
        "#1E88E5":"#64B5F6", "#43A047":"#81C784", "#FDD835":"#FFF59D",
        "#FB8C00":"#FFCC80", "#795548":"#BCAAA4", "#8E24AA":"#CE93D8",
        "#EC407A":"#F8BBD0", "#26A69A":"#80CBC4"
    }
    dark_map = {
        "#FFFFFF":"#BDBDBD", "#9E9E9E":"#616161", "#E53935":"#B71C1C",
        "#1E88E5":"#0D47A1", "#43A047":"#1B5E20", "#FDD835":"#F9A825",
        "#FB8C00":"#E65100", "#795548":"#4E342E", "#8E24AA":"#6A1B9A",
        "#EC407A":"#C2185B", "#26A69A":"#00695C"
    }

    for names, base in bases:
        if any(n in text or n in compact for n in names):
            if is_light:
                return light_map.get(base, base)
            if is_dark:
                return dark_map.get(base, base)
            return base

    # Nur wirklich unbekannte Farben bleiben neutral grau.
    return "#BDBDBD"

def refresh_overview_color_boxes():
    if "overview_color_boxes" not in globals(): return
    for w in overview_color_boxes.winfo_children(): w.destroy()
    pid=int(printer_selected.get() or 0)
    if not pid:
        tk.Label(overview_color_boxes,text="Drucker auswählen",bg=CREAM,fg=GREY).pack(side="left")
        return
    with con() as c:
        rows=c.execute("""SELECT s.slot_nr,COALESCE(f.farbe,'')
                          FROM drucker_slots s LEFT JOIN filamente f ON f.id=s.filament_id
                          WHERE s.drucker_id=? ORDER BY s.slot_nr""",(pid,)).fetchall()
        rr=c.execute("SELECT COALESCE(filamentplaetze,1) FROM drucker WHERE id=?",(pid,)).fetchone()
    byslot={int(n):farbe for n,farbe in rows}
    count=min(10,max(1,int((rr[0] if rr else 1) or 1)))
    for n in range(1,count+1):
        farbe=byslot.get(n,"")
        bg=filament_display_color(farbe)
        fg="#FFFFFF" if bg in ("#111111","#E53935","#1E88E5","#43A047","#795548","#8E24AA") else "#111111"
        selected=(str(slot_no_var.get())==str(n)) if "slot_no_var" in globals() else False
        box=tk.Label(overview_color_boxes,text=str(n),bg=bg,fg=fg,width=3,height=1,
                     relief="solid",bd=3 if selected else 1,font=("Segoe UI",9,"bold"),cursor="hand2")
        box.pack(side="left",padx=2)
        box.bind("<Button-1>",lambda e,slot=n: choose_slot_from_box(slot))
        hint=f"Slot {n}: {farbe}" if farbe else f"Slot {n}: frei"
        box.bind("<Enter>",lambda e,t=hint: overview_color_hint.set(t))
        box.bind("<Leave>",lambda e: overview_color_hint.set(""))

def choose_slot_from_box(n):
    """Slot per Klick auf das Farbfeld auswählen."""
    slot_no_var.set(str(n))
    pid=int(printer_selected.get() or 0)
    if not pid:
        return
    with con() as c:
        r=c.execute("""SELECT f.hersteller,f.farbe,f.material,f.ausfuehrung
                       FROM drucker_slots s
                       LEFT JOIN filamente f ON f.id=s.filament_id
                       WHERE s.drucker_id=? AND s.slot_nr=?""",(pid,n)).fetchone()
    if r and r[0]:
        slot_filament_var.set(f"{r[0]} | {r[1]} | {r[2]} | {r[3]}")
    else:
        slot_filament_var.set("— frei —")
    refresh_color_boxes()
    refresh_overview_color_boxes()

def refresh_color_boxes():
    if "color_boxes_frame" not in globals(): return
    for w in color_boxes_frame.winfo_children(): w.destroy()
    pid=int(printer_selected.get() or 0)
    if not pid:
        tk.Label(color_boxes_frame,text="Drucker auswählen",bg=WHITE,fg=GREY).pack(side="left")
        return
    with con() as c:
        rows=c.execute("""SELECT s.slot_nr,COALESCE(f.farbe,'') FROM drucker_slots s
                          LEFT JOIN filamente f ON f.id=s.filament_id
                          WHERE s.drucker_id=? ORDER BY s.slot_nr""",(pid,)).fetchall()
    # Common German/English filament color names -> display color.
    cmap={"schwarz":"#111111","black":"#111111","weiß":"#FFFFFF","weiss":"#FFFFFF","white":"#FFFFFF",
          "rot":"#E53935","red":"#E53935","blau":"#1E88E5","blue":"#1E88E5","grün":"#43A047","green":"#43A047",
          "gelb":"#FDD835","yellow":"#FDD835","orange":"#FB8C00","grau":"#9E9E9E","grey":"#9E9E9E","gray":"#9E9E9E",
          "silber":"#C0C0C0","silver":"#C0C0C0","gold":"#D4AF37","braun":"#795548","brown":"#795548",
          "lila":"#8E24AA","violett":"#8E24AA","purple":"#8E24AA","pink":"#EC407A","rosa":"#EC407A",
          "türkis":"#26A69A","turkis":"#26A69A","cyan":"#00ACC1","beige":"#D7CCC8"}
    byslot={int(n):f for n,f in rows}
    with con() as c:
        rr=c.execute("SELECT filamentplaetze FROM drucker WHERE id=?",(pid,)).fetchone()
    count=min(10,max(1,int((rr[0] if rr else 1) or 1)))
    for n in range(1,count+1):
        farbe=byslot.get(n,"")
        bg=cmap.get(farbe.strip().lower(),"#E5E7EB" if not farbe else "#BDBDBD")
        selected=(str(slot_no_var.get())==str(n))
        box=tk.Label(color_boxes_frame,text=str(n),bg=bg,
                     fg="#FFFFFF" if bg in ("#111111","#E53935","#1E88E5","#43A047","#795548","#8E24AA") else "#111111",
                     width=3,height=1,relief="solid",bd=3 if selected else 1,
                     font=("Segoe UI",9,"bold"),cursor="hand2")
        box.pack(side="left",padx=2)
        box.bind("<Button-1>",lambda e,slot=n: choose_slot_from_box(slot))
        if farbe:
            try:
                box.bind("<Enter>",lambda e,t=f"Slot {n}: {farbe}": color_hint.set(t))
                box.bind("<Leave>",lambda e: color_hint.set(""))
            except: pass

def slot_refresh():
    if "slot_tree" not in globals(): return
    for x in slot_tree.get_children(): slot_tree.delete(x)
    pid=int(printer_selected.get() or 0)
    if not pid: return
    with con() as c:
        rows=c.execute("""SELECT s.slot_nr,f.hersteller,f.farbe,f.material,f.ausfuehrung
                          FROM drucker_slots s LEFT JOIN filamente f ON f.id=s.filament_id
                          WHERE s.drucker_id=? ORDER BY s.slot_nr""",(pid,)).fetchall()
    for r in rows:
        slot_tree.insert("", "end", values=(r[0],r[1] or "",r[2] or "",r[3] or "",r[4] or "",
                                            "belegt" if r[1] else "frei"))

def slot_select(_=None):
    sel=slot_tree.selection()
    if not sel: return
    vals=slot_tree.item(sel[0],"values")
    slot_no_var.set(int(vals[0]))
    if vals[1]:
        label=f"{vals[1]} | {vals[2]} | {vals[3]} | {vals[4]}"
        slot_filament_var.set(label)
    else:
        slot_filament_var.set("— frei —")

def slot_save():
    if not printer_selected.get():
        messagebox.showinfo("Filament-Slots","Bitte zuerst einen Drucker auswählen.")
        return
    if not str(slot_no_var.get()).strip():
        messagebox.showinfo("Filament-Slots","Bitte zuerst einen Slot auswählen.")
        return
    n=int(slot_no_var.get())
    label=slot_filament_var.get()
    fid=slot_filament_map.get(label)
    with con() as c:
        c.execute("""INSERT INTO drucker_slots(drucker_id,slot_nr,filament_id) VALUES(?,?,?)
                     ON CONFLICT(drucker_id,slot_nr) DO UPDATE SET filament_id=excluded.filament_id""",
                  (int(printer_selected.get()),n,fid))
    slot_refresh(); printer_refresh(); refresh_color_boxes(); refresh_overview_color_boxes(); printer_tree.after_idle(draw_printer_tree_color_boxes)

def slot_clear():
    if not printer_selected.get(): return
    if not str(slot_no_var.get()).strip():
        messagebox.showinfo("Filament-Slots","Bitte zuerst einen Slot auswählen.")
        return
    n=int(slot_no_var.get())
    with con() as c:
        c.execute("UPDATE drucker_slots SET filament_id=NULL WHERE drucker_id=? AND slot_nr=?",
                  (int(printer_selected.get()),n))
    slot_filament_var.set("— frei —"); slot_refresh(); printer_refresh(); refresh_color_boxes(); refresh_overview_color_boxes(); printer_tree.after_idle(draw_printer_tree_color_boxes); printer_tree.after_idle(draw_printer_tree_color_boxes)

def printer_clear():
    printer_selected.set("")
    for v in PV.values(): v.set("")
    PV["druckernummer"].set(next_printer_number())
    if "slot_no_var" in globals(): slot_no_var.set("")
    if "slot_no_box" in globals(): slot_no_box["values"]=[]

def printer_pick(_=None):
    sel=printer_tree.selection()
    if not sel:return
    r=printer_tree.item(sel[0],"values")
    printer_selected.set(r[0])
    for k,v in zip(["druckernummer","name","hersteller","modell","ip","standort","notizen"],r[1:8]): PV[k].set(v)
    with con() as c:
        rr=c.execute("SELECT COALESCE(filamentplaetze,1) FROM drucker WHERE id=?",(r[0],)).fetchone()
    PV.get("filamentplaetze", tk.StringVar()).set(rr[0] if rr else 1)
    ensure_printer_slots(r[0],PV.get("filamentplaetze", tk.StringVar(value="1")).get())
    count=min(10,max(1,int(PV.get("filamentplaetze", tk.StringVar(value="1")).get() or 1)))
    if "slot_no_box" in globals(): slot_no_box["values"]=[str(n) for n in range(1,count+1)]
    slot_no_var.set("")
    refresh_slot_filament_choices(); slot_refresh(); refresh_color_boxes(); refresh_overview_color_boxes()


def printer_save():
    x={k:(v.get().strip() if k!="filamentplaetze" else min(10,max(1,int(v.get() or 1)))) for k,v in PV.items()}
    if not x["name"]:
        messagebox.showwarning("Drucker","Bitte einen Druckernamen eingeben."); return
    if not x["druckernummer"]:
        x["druckernummer"]=next_printer_number()
    d=(x["druckernummer"].upper(),x["name"],x["hersteller"],x["modell"],x["ip"],x["standort"],x["notizen"],x["filamentplaetze"])
    try:
        with con() as c:
            exists=c.execute("SELECT id FROM drucker WHERE UPPER(TRIM(druckernummer))=? AND id<>?",
                             (x["druckernummer"].upper(), int(printer_selected.get() or 0))).fetchone()
            if exists:
                messagebox.showwarning("Drucker","Diese Druckernummer ist bereits vergeben."); return
            if printer_selected.get():
                pid=int(printer_selected.get())
                c.execute("""UPDATE drucker SET druckernummer=?,name=?,hersteller=?,modell=?,ip=?,standort=?,notizen=?,filamentplaetze=?
                             WHERE id=?""",d+(pid,))
            else:
                cur=c.execute("""INSERT INTO drucker(druckernummer,name,hersteller,modell,ip,standort,notizen,filamentplaetze)
                                 VALUES(?,?,?,?,?,?,?,?)""",d)
                pid=cur.lastrowid
        ensure_printer_slots(pid,x["filamentplaetze"])
    except Exception as e:
        messagebox.showerror("Drucker",f"Drucker konnte nicht gespeichert werden:\n{e}"); return
    printer_clear(); refresh_printer_manufacturers(); printer_refresh(); refresh_slot_filament_choices(); slot_refresh()


def printer_delete():
    if not printer_selected.get():
        messagebox.showinfo("Drucker","Bitte zuerst einen Drucker auswählen."); return
    if messagebox.askyesno("Drucker löschen","Ausgewählten Drucker wirklich löschen?"):
        pid=str(printer_selected.get())
        with con() as c: c.execute("DELETE FROM drucker WHERE id=?",(pid,))
        printer_status_cache.pop(pid,None)
        printer_clear(); refresh_printer_manufacturers(); printer_refresh()

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
root=tk.Tk(); root.title("Juno modellbau – Lager & Drucker V5.6.5"); root.geometry("1420x980"); root.minsize(1100,760); root.configure(bg=CREAM)
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
PV={k:tk.StringVar() for k in ["druckernummer","name","hersteller","modell","ip","standort","notizen","filamentplaetze"]}
PV["filamentplaetze"].set("1")
printer_status_cache={}
printer_checking=tk.BooleanVar(value=False)
printer_status_text=tk.StringVar(value="Noch nicht geprüft")
printer_search=tk.StringVar()

pcard=tk.Frame(printer_page,bg=WHITE,highlightbackground="#D9DDE2",highlightthickness=1)
pcard.pack(fill="x",padx=8,pady=(8,0))
tk.Label(pcard,text="Druckerverwaltung",bg=WHITE,fg=NAVY,font=("Segoe UI",14,"bold")).grid(row=0,column=0,columnspan=8,sticky="w",padx=14,pady=12)
pfields=[("Druckernummer","druckernummer"),("Druckername","name"),("Hersteller","hersteller"),("Modell","modell"),
         ("IP-Adresse","ip"),("Standort","standort"),("Notizen","notizen"),("Filamentplätze","filamentplaetze")]
pwidgets={}
for i,(lab,k) in enumerate(pfields):
    tk.Label(pcard,text=lab,bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).grid(row=1,column=i,sticky="w",padx=10)
    if k=="hersteller":
        w=ttk.Combobox(pcard,textvariable=PV[k])
    elif k=="filamentplaetze":
        w=tk.Spinbox(pcard,from_=1,to=10,textvariable=PV[k],width=8)
    else:
        w=ttk.Entry(pcard,textvariable=PV[k])
    w.grid(row=2,column=i,sticky="ew",padx=10,pady=(2,10),ipady=3)
    pwidgets[k]=w
    pcard.grid_columnconfigure(i,weight=1)
printer_manufacturer_box=pwidgets["hersteller"]
pbuttons=tk.Frame(pcard,bg=WHITE); pbuttons.grid(row=3,column=0,columnspan=8,sticky="w",padx=10,pady=(0,14))
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
pcols=("id","druckernummer","name","hersteller","modell","ip","standort","notizen","farben","status")
pheads=["ID","Nr.","Druckername","Hersteller","Modell","IP-Adresse","Standort","Notizen","Farben geladen","Status"]
printer_tree=ttk.Treeview(pbox,columns=pcols,show="headings",height=6)
for c,h in zip(pcols,pheads): printer_tree.heading(c,text=h)
printer_tree.column("id",width=0,stretch=False)
for c,w in zip(pcols[1:],[60,125,105,115,120,115,135,260,95]): printer_tree.column(c,width=w)
printer_tree.tag_configure("online",background="#D9F2DD")
printer_tree.tag_configure("offline",background="#FFD0D0")
printer_tree.tag_configure("unknown",background="#FFF2B2")
pys=ttk.Scrollbar(pbox,orient="vertical",command=printer_tree.yview); printer_tree.configure(yscrollcommand=pys.set)
printer_tree.pack(side="left",fill="both",expand=True); pys.pack(side="right",fill="y")
printer_tree.bind("<<TreeviewSelect>>",printer_pick)
printer_tree.bind("<Configure>",lambda e: printer_tree.after_idle(draw_printer_tree_color_boxes))
printer_tree.bind("<MouseWheel>",lambda e: printer_tree.after(30,draw_printer_tree_color_boxes),add="+")


# Farbige Slot-Kästchen direkt in der Spalte "Farben geladen"
printer_color_widgets=[]

def draw_printer_tree_color_boxes():
    global printer_color_widgets
    for w in printer_color_widgets:
        try: w.destroy()
        except: pass
    printer_color_widgets=[]
    try:
        printer_tree.update_idletasks()
        for item in printer_tree.get_children():
            vals=printer_tree.item(item,"values")
            if not vals: continue
            pid=int(vals[0])
            bbox=printer_tree.bbox(item,"farben")
            if not bbox: continue
            x,y,w,h=bbox
            with con() as c:
                rows=c.execute("""SELECT s.slot_nr,COALESCE(f.farbe,'')
                                  FROM drucker_slots s
                                  LEFT JOIN filamente f ON f.id=s.filament_id
                                  WHERE s.drucker_id=? ORDER BY s.slot_nr""",(pid,)).fetchall()
                rr=c.execute("SELECT COALESCE(filamentplaetze,1) FROM drucker WHERE id=?",(pid,)).fetchone()
            byslot={int(n):farbe for n,farbe in rows}
            count=min(10,max(1,int((rr[0] if rr else 1) or 1)))
            size=max(18,min(24,h-4))
            gap=3
            start=x+5
            for n in range(1,count+1):
                farbe=byslot.get(n,"")
                bg=filament_display_color(farbe)
                fg="#FFFFFF" if bg in ("#111111","#E53935","#1E88E5","#43A047","#795548","#8E24AA") else "#111111"
                lab=tk.Label(printer_tree,text=str(n),bg=bg,fg=fg,bd=1,relief="solid",
                             font=("Segoe UI",8,"bold"),cursor="hand2")
                lab.place(x=start+(n-1)*(size+gap),y=y+2,width=size,height=max(16,h-4))
                lab.bind("<Button-1>",lambda e,p=pid,slot=n: select_printer_slot_from_overview(p,slot))
                printer_color_widgets.append(lab)
    except Exception:
        pass

def select_printer_slot_from_overview(pid, slot):
    # Passenden Drucker markieren und danach den geklickten Slot auswählen.
    for item in printer_tree.get_children():
        vals=printer_tree.item(item,"values")
        if vals and int(vals[0])==int(pid):
            printer_tree.selection_set(item)
            printer_tree.focus(item)
            printer_tree.see(item)
            printer_pick()
            choose_slot_from_box(slot)
            break

# Schnelle Farbübersicht für den aktuell markierten Drucker
overview_colors=tk.Frame(printer_page,bg=CREAM)
overview_colors.pack(fill="x",padx=12,pady=(0,6))
tk.Label(overview_colors,text="Farben des ausgewählten Druckers:",bg=CREAM,fg=NAVY,
         font=("Segoe UI",9,"bold")).pack(side="left",padx=(0,8))
overview_color_boxes=tk.Frame(overview_colors,bg=CREAM)
overview_color_boxes.pack(side="left")
overview_color_hint=tk.StringVar(value="")
tk.Label(overview_colors,textvariable=overview_color_hint,bg=CREAM,fg=GREY,
         font=("Segoe UI",9)).pack(side="left",padx=10)



# Filament-Slots pro Drucker
slotbox=tk.LabelFrame(printer_page,text=" Filamentbelegung des ausgewählten Druckers ",bg=WHITE,fg=NAVY,
                      font=("Segoe UI",11,"bold"),padx=10,pady=8)
slotbox.pack(fill="both",expand=True,padx=12,pady=(0,8))
slot_no_var=tk.StringVar(value="")
slot_filament_var=tk.StringVar(value="— frei —")
tk.Label(slotbox,text="Slot",bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).grid(row=0,column=0,sticky="w")
slot_no_box=ttk.Combobox(slotbox,textvariable=slot_no_var,state="readonly",width=8,values=[])
slot_no_box.grid(row=1,column=0,padx=(0,10),sticky="w")
tk.Label(slotbox,text="Filament aus Lager",bg=WHITE,fg=TEXT,font=("Segoe UI",9,"bold")).grid(row=0,column=1,sticky="w")
slot_filament_box=ttk.Combobox(slotbox,textvariable=slot_filament_var,state="readonly",width=52)
slot_filament_box.grid(row=1,column=1,padx=(0,10),sticky="w")
tk.Button(slotbox,text="Filament zuordnen",command=slot_save,bg=NAVY,fg="white",font=("Segoe UI",9,"bold"),bd=0,padx=12,pady=7).grid(row=1,column=2,padx=4)
tk.Button(slotbox,text="Slot leeren",command=slot_clear,bg=GREY,fg="white",font=("Segoe UI",9,"bold"),bd=0,padx=12,pady=7).grid(row=1,column=3,padx=4)

slotcols=("slot","hersteller","farbe","material","ausfuehrung","status")
color_hint=tk.StringVar(value="")
tk.Label(slotbox,text="Geladene Farben",bg=WHITE,fg=NAVY,font=("Segoe UI",9,"bold")).grid(row=2,column=0,sticky="w",pady=(10,4))
color_boxes_frame=tk.Frame(slotbox,bg=WHITE)
color_boxes_frame.grid(row=2,column=1,columnspan=2,sticky="w",pady=(10,4))
tk.Label(slotbox,textvariable=color_hint,bg=WHITE,fg=GREY,font=("Segoe UI",9)).grid(row=2,column=3,sticky="w",pady=(10,4))

slot_tree=ttk.Treeview(slotbox,columns=slotcols,show="headings",height=10)
for c,t,w in [("slot","Slot",55),("hersteller","Hersteller",160),("farbe","Farbe",150),
              ("material","Material",100),("ausfuehrung","Ausführung",120),("status","Status",90)]:
    slot_tree.heading(c,text=t); slot_tree.column(c,width=w,anchor="center" if c in ("slot","status") else "w")
slot_tree.grid(row=3,column=0,columnspan=4,sticky="nsew",pady=(8,0))
slot_scroll=ttk.Scrollbar(slotbox,orient="vertical",command=slot_tree.yview)
slot_tree.configure(yscrollcommand=slot_scroll.set)
slot_scroll.grid(row=3,column=4,sticky="ns",pady=(8,0))
slot_tree.bind("<<TreeviewSelect>>",slot_select)
slotbox.grid_columnconfigure(1,weight=1)
slotbox.grid_rowconfigure(3,weight=1)

clear(); refresh_lists(); refresh(); printer_clear(); refresh_printer_manufacturers(); printer_refresh(); refresh_slot_filament_choices(); refresh_color_boxes(); refresh_overview_color_boxes()
root.after(1200,schedule_printer_check)
root.after(150,draw_printer_tree_color_boxes)
root.mainloop()

