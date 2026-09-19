import ttkbootstrap as tb
from ttkbootstrap.constants import *
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk
import sqlite3
import json
import os
import sys
import shutil
import hashlib
import csv
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

# PDF Generation Support
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def get_asset_path(filename):
    """Resolve asset path for PyInstaller packages and direct script execution."""
    if hasattr(sys, '_MEIPASS'):
        bundle_path = os.path.join(sys._MEIPASS, filename)
        if os.path.exists(bundle_path):
            return bundle_path
    
    exe_dir_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), filename)
    if os.path.exists(exe_dir_path):
        return exe_dir_path
        
    return filename


class SecurityManager:
    """Local application authentication using PBKDF2-HMAC-SHA256."""
    def __init__(self, app_dir):
        self.app_dir = app_dir
        self.auth_file = os.path.join(app_dir, "auth.dat")

    def _hash(self, password, salt):
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, 200_000
        ).hex()

    def exists(self):
        return os.path.exists(self.auth_file)

    def set_password(self, password):
        salt = os.urandom(16)
        digest = self._hash(password, salt)
        with open(self.auth_file, "w", encoding="utf-8") as f:
            f.write(f"{salt.hex()}:{digest}")

    def verify(self, password):
        try:
            salt_hex, digest = open(self.auth_file, encoding="utf-8").read().strip().split(":", 1)
            salt = bytes.fromhex(salt_hex)
            return self._hash(password, salt) == digest
        except Exception:
            return False


class LoginWindow:
    """Simple local login gate to control application access."""
    def __init__(self, root, on_success):
        self.root = root
        self.on_success = on_success
        self.app_dir = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")), "ApexTaxPro"
        )
        os.makedirs(self.app_dir, exist_ok=True)
        self.security = SecurityManager(self.app_dir)

        self.win = tb.Toplevel(root)
        self.win.title("ApexTax Pro - Secure Login")
        self.win.geometry("420x300")
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", root.destroy)
        self.win.grab_set()

        tb.Label(
            self.win, text="🔐 ApexTax Pro", font=("Helvetica", 20, "bold"),
            bootstyle="primary"
        ).pack(pady=(28, 8))
        tb.Label(
            self.win,
            text="Local application access",
            font=("Helvetica", 10)
        ).pack(pady=(0, 18))

        self.password = tb.Entry(self.win, width=30, show="•")
        self.password.pack(pady=8)
        self.password.focus_set()

        if self.security.exists():
            self.mode = "login"
            self.button_text = "🔓 Sign In"
            self.help_text = "Enter your ApexTax Pro password."
        else:
            self.mode = "setup"
            self.button_text = "🔐 Create Password"
            self.help_text = "First run: create a local application password."

        tb.Label(self.win, text=self.help_text).pack(pady=5)
        tb.Button(
            self.win, text=self.button_text, bootstyle="success",
            command=self.submit
        ).pack(pady=18, ipadx=20)
        self.win.bind("<Return>", lambda e: self.submit())

    def submit(self):
        value = self.password.get()
        if len(value) < 6:
            return messagebox.showwarning(
                "Password", "Use at least 6 characters.", parent=self.win
            )

        if self.mode == "setup":
            self.security.set_password(value)
            messagebox.showinfo(
                "Password Created",
                "Your local ApexTax Pro password has been created.",
                parent=self.win
            )
            self.win.destroy()
            self.on_success()
            return

        if self.security.verify(value):
            self.win.destroy()
            self.on_success()
        else:
            self.password.delete(0, END)
            messagebox.showerror(
                "Access Denied", "Incorrect password.", parent=self.win
            )


class TaxVaultMasterERP:
    def __init__(self, root):
        self.root = root
        self.root.title("ApexTax Pro - Enterprise GST Master Suite")
        self.root.geometry("1240x900")
        
        # Configure Enterprise AppData Directories
        self.app_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'ApexTaxPro')
        if not os.path.exists(self.app_dir):
            os.makedirs(self.app_dir, exist_ok=True)
        self.db_path = os.path.join(self.app_dir, 'tax_vault_master.db')
        self.security = SecurityManager(self.app_dir)
        
        # Window Icon Setup
        logo_path = get_asset_path("logo.png")
        try:
            if os.path.exists(logo_path):
                ico = Image.open(logo_path)
                self.window_icon = ImageTk.PhotoImage(ico)
                self.root.iconphoto(True, self.window_icon)
        except Exception:
            pass

        self.setup_db()
        self.setup_menus()
        self.setup_master_header()
        
        # Modern Tabbed Navigation
        self.notebook = tb.Notebook(self.root, bootstyle="info")
        self.notebook.pack(fill=BOTH, expand=True, padx=20, pady=10)
        
        self.tab_sales = tb.Frame(self.notebook)
        self.tab_purch = tb.Frame(self.notebook)
        self.tab_gstr3b = tb.Frame(self.notebook)
        
        self.notebook.add(self.tab_sales, text=" 📈 Step 1: GSTR-1 (Sales Register) ")
        self.notebook.add(self.tab_purch, text=" 🛒 Step 2: Purchase Register (ITC) ")
        self.notebook.add(self.tab_gstr3b, text=" 📊 Step 3: GSTR-3B (Auto-Dashboard) ")
        
        self.build_sales_tab()
        self.build_purchases_tab()
        self.build_gstr3b_tab()
        
        self.refresh_seller_list()
        self.refresh_customer_list()
        self.refresh_year_list()
        self.load_all_data()

    # ==========================================
    # ENTERPRISE MENU / BACKUP / EXPORT TOOLS
    # ==========================================
    def setup_menus(self):
        menubar = tb.Menu(self.root)

        file_menu = tb.Menu(menubar, tearoff=0)
        file_menu.add_command(label="💾 Backup Database", command=self.backup_database)
        file_menu.add_command(label="♻ Restore Database", command=self.restore_database)
        file_menu.add_separator()
        file_menu.add_command(label="📂 Open App Data Folder", command=self.open_app_folder)
        file_menu.add_command(label="🚪 Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tb.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="📊 Export Sales CSV", command=self.export_sales_csv)
        tools_menu.add_command(label="📊 Export Purchases CSV", command=self.export_purchases_csv)
        tools_menu.add_command(label="🔐 Change Password", command=self.change_password)
        tools_menu.add_separator()
        tools_menu.add_command(label="🧹 Clear Sale Form", command=self.clear_sale_form)
        tools_menu.add_command(label="🧹 Clear Purchase Form", command=self.clear_purchase_form)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tb.Menu(menubar, tearoff=0)
        help_menu.add_command(
            label="About",
            command=lambda: messagebox.showinfo(
                "About ApexTax Pro",
                "ApexTax Pro - Enterprise GST Master Suite\n\n"
                "Local SQLite ERP with sales, purchases, PDF invoices, "
                "GSTR-1 JSON export and GSTR-3B calculations."
            )
        )
        help_menu.add_command(
            label="GST Compliance Note",
            command=lambda: messagebox.showinfo(
                "Compliance Note",
                "This application automates calculations and data preparation. "
                "GST return schemas, thresholds, classifications, ITC eligibility "
                "and filing requirements can change. Verify the current official "
                "GST specifications before filing."
            )
        )
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def clear_sale_form(self):
        for widget in (
            self.ent_customer_name, self.ent_customer_gstin, self.ent_bill_no,
            self.ent_hsn, self.ent_item, self.ent_qty, self.ent_rate
        ):
            widget.delete(0, END)
        self.ent_pos.delete(0, END)
        self.ent_pos.insert(0, "24")
        self.ent_tax_rate.delete(0, END)
        self.ent_tax_rate.insert(0, "18")
        self.ent_bill_date.delete(0, END)
        self.ent_bill_date.insert(0, datetime.now().strftime("%d-%m-%Y"))
        self.combo_buyer_select.set("")

    def clear_purchase_form(self):
        for widget in (
            self.p_vendor_name, self.p_vendor_gstin, self.p_bill_no,
            self.p_hsn, self.p_item, self.p_qty, self.p_rate
        ):
            widget.delete(0, END)
        self.p_tax_rate.delete(0, END)
        self.p_tax_rate.insert(0, "18")
        self.p_bill_date.delete(0, END)
        self.p_bill_date.insert(0, datetime.now().strftime("%d-%m-%Y"))

    def open_app_folder(self):
        try:
            if sys.platform.startswith("win"):
                os.startfile(self.app_dir)
            elif sys.platform == "darwin":
                os.system(f'open "{self.app_dir}"')
            else:
                os.system(f'xdg-open "{self.app_dir}"')
        except Exception as e:
            messagebox.showerror("Open Folder", str(e))

    def change_password(self):
        popup = tb.Toplevel(self.root)
        popup.title("Change Password")
        popup.geometry("400x270")
        popup.grab_set()

        tb.Label(popup, text="Current password").grid(row=0, column=0, padx=15, pady=12, sticky=W)
        old = tb.Entry(popup, width=25, show="•")
        old.grid(row=0, column=1)

        tb.Label(popup, text="New password").grid(row=1, column=0, padx=15, pady=12, sticky=W)
        new = tb.Entry(popup, width=25, show="•")
        new.grid(row=1, column=1)

        tb.Label(popup, text="Confirm password").grid(row=2, column=0, padx=15, pady=12, sticky=W)
        confirm = tb.Entry(popup, width=25, show="•")
        confirm.grid(row=2, column=1)

        def save():
            if not self.security.verify(old.get()):
                return messagebox.showerror("Password", "Current password is incorrect.", parent=popup)
            if len(new.get()) < 6:
                return messagebox.showwarning("Password", "New password must be at least 6 characters.", parent=popup)
            if new.get() != confirm.get():
                return messagebox.showerror("Password", "New passwords do not match.", parent=popup)
            self.security.set_password(new.get())
            popup.destroy()
            messagebox.showinfo("Password", "Password changed successfully.")

        tb.Button(
            popup, text="Save New Password", bootstyle="success",
            command=save
        ).grid(row=3, column=0, columnspan=2, pady=18)

    def restore_database(self):
        path = filedialog.askopenfilename(
            title="Select ApexTax Pro SQLite backup",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")]
        )
        if not path:
            return
        if not messagebox.askyesno(
            "Restore Database",
            "Restoring will replace the current database after a safety backup. Continue?"
        ):
            return

        try:
            self.backup_database(show_message=False)
            self.conn.close()
            shutil.copy2(path, self.db_path)
            self.conn = sqlite3.connect(self.db_path)
            self.c = self.conn.cursor()
            self.load_all_data()
            self.refresh_seller_list()
            self.refresh_customer_list()
            self.refresh_year_list()
            messagebox.showinfo("Restore Complete", "Database restored successfully.")
        except Exception as e:
            messagebox.showerror("Restore Failed", str(e))

    def _export_table_csv(self, table_name, filename_prefix, columns, query):
        path = filedialog.asksaveasfilename(
            title=f"Export {filename_prefix}",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if not path:
            return
        try:
            self.c.execute(query, (self.combo_seller_select.get(),))
            rows = self.c.fetchall()
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
            messagebox.showinfo("CSV Export", f"Exported {len(rows)} rows to:\n{path}")
        except Exception as e:
            messagebox.showerror("CSV Export Failed", str(e))

    def export_sales_csv(self):
        self._export_table_csv(
            "invoices", "Sales_Register",
            ["ID", "Bill No", "Date", "Customer", "GSTIN", "POS",
             "Taxable", "CGST", "SGST", "IGST", "Total"],
            """SELECT id, bill_no, bill_date, customer_name, customer_gstin,
                      pos, taxable_val, cgst, sgst, igst, total_amount
               FROM invoices WHERE seller_name=? ORDER BY id DESC"""
        )

    def export_purchases_csv(self):
        self._export_table_csv(
            "purchases", "Purchase_Register",
            ["ID", "Bill No", "Date", "Vendor", "GSTIN",
             "Taxable", "CGST", "SGST", "IGST", "Total"],
            """SELECT id, bill_no, bill_date, vendor_name, vendor_gstin,
                      taxable_val, cgst, sgst, igst, total_amount
               FROM purchases WHERE seller_name=? ORDER BY id DESC"""
        )

    # ==========================================
    # DATABASE SETUP (ATOMIC & PERSISTENT)
    # ==========================================
    def setup_db(self):
        self.conn = sqlite3.connect(self.db_path)
        with self.conn:
            self.c = self.conn.cursor()
            self.c.execute('''CREATE TABLE IF NOT EXISTS sellers 
                              (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, address TEXT, gstin TEXT)''')
            
            self.c.execute('''CREATE TABLE IF NOT EXISTS customers 
                              (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, phone TEXT, address TEXT, gstin TEXT, state_code TEXT)''')
                               
            self.c.execute('''CREATE TABLE IF NOT EXISTS invoices 
                              (id INTEGER PRIMARY KEY AUTOINCREMENT, seller_name TEXT, seller_gstin TEXT, 
                               customer_name TEXT, customer_gstin TEXT, pos TEXT, bill_no TEXT, bill_date TEXT, bill_year TEXT, 
                               hsn_code TEXT, item_name TEXT, qty REAL, rate REAL, taxable_val REAL, 
                               tax_rate REAL, cgst REAL, sgst REAL, igst REAL, total_amount REAL)''')
                               
            self.c.execute('''CREATE TABLE IF NOT EXISTS purchases 
                              (id INTEGER PRIMARY KEY AUTOINCREMENT, seller_name TEXT, seller_gstin TEXT, 
                               vendor_name TEXT, vendor_gstin TEXT, bill_no TEXT, bill_date TEXT, bill_year TEXT, 
                               hsn_code TEXT, item_name TEXT, qty REAL, rate REAL, taxable_val REAL, 
                               tax_rate REAL, cgst REAL, sgst REAL, igst REAL, total_amount REAL)''')

    # ==========================================
    # MASTER CLIENT HEADER
    # ==========================================
    def setup_master_header(self):
        header_frame = tb.LabelFrame(self.root, text="🏢 APEXTAX PRO: Select Active Taxpayer (Your Client)", bootstyle="primary", padding=15)
        header_frame.pack(fill=X, padx=20, pady=15)

        logo_path = get_asset_path("logo.png")
        try:
            if os.path.exists(logo_path):
                img = Image.open(logo_path)
                img = img.resize((32, 32), Image.Resampling.LANCZOS)
                self.header_logo = ImageTk.PhotoImage(img)
                logo_label = tb.Label(header_frame, image=self.header_logo)
                logo_label.pack(side=LEFT, padx=(0, 10))
        except Exception:
            pass

        tb.Label(header_frame, text="Active Client:", font=("Helvetica", 10, "bold")).pack(side=LEFT, padx=5)
        self.combo_seller_select = tb.Combobox(header_frame, width=30, state="readonly", bootstyle="primary")
        self.combo_seller_select.pack(side=LEFT, padx=10)
        self.combo_seller_select.bind("<<ComboboxSelected>>", self.on_seller_selected)

        tb.Label(header_frame, text="Client GSTIN:", font=("Helvetica", 10)).pack(side=LEFT, padx=10)
        self.lbl_active_gstin = tb.Label(header_frame, text="[Not Selected]", font=("Helvetica", 11, "bold"), bootstyle="danger")
        self.lbl_active_gstin.pack(side=LEFT, padx=5)
        
        tb.Button(header_frame, text="➕ Add New Client", bootstyle="outline-primary", command=self.open_add_seller_window).pack(side=RIGHT, padx=10)
        tb.Button(
            header_frame, text="💾 Backup Now", bootstyle="outline-success",
            command=self.backup_database
        ).pack(side=RIGHT, padx=5)

    # ==========================================
    # TAB 1: GSTR-1 (SALES REGISTER)
    # ==========================================
    def build_sales_tab(self):
        entry_f = tb.LabelFrame(self.tab_sales, text="🧾 Enter Customer Sales", bootstyle="info", padding=15)
        entry_f.pack(fill=X, padx=15, pady=10)

        # Row 0: Buyer Account Info
        tb.Label(entry_f, text="Select Buyer Account:").grid(row=0, column=0, sticky=W, padx=5, pady=5)
        self.combo_buyer_select = tb.Combobox(entry_f, width=18, state="readonly")
        self.combo_buyer_select.grid(row=0, column=1, padx=5, pady=5)
        self.combo_buyer_select.bind("<<ComboboxSelected>>", self.on_customer_selected)
        
        tb.Button(entry_f, text="➕ Add Buyer", bootstyle="outline-info", command=self.open_add_customer_window).grid(row=0, column=2, padx=5, pady=5)

        tb.Label(entry_f, text="Customer Name:").grid(row=0, column=3, sticky=W, padx=5, pady=5)
        self.ent_customer_name = tb.Entry(entry_f, width=18)
        self.ent_customer_name.grid(row=0, column=4, padx=5, pady=5)

        tb.Label(entry_f, text="Customer GSTIN:").grid(row=0, column=5, sticky=W, padx=5, pady=5)
        self.ent_customer_gstin = tb.Entry(entry_f, width=15)
        self.ent_customer_gstin.grid(row=0, column=6, padx=5, pady=5)

        tb.Label(entry_f, text="POS (State):").grid(row=0, column=7, sticky=W, padx=5, pady=5)
        self.ent_pos = tb.Entry(entry_f, width=5)
        self.ent_pos.grid(row=0, column=8, padx=5, pady=5)
        self.ent_pos.insert(0, "24")

        # Row 1: Invoice Details
        tb.Label(entry_f, text="Bill No:").grid(row=1, column=0, sticky=W, padx=5, pady=5)
        self.ent_bill_no = tb.Entry(entry_f, width=12)
        self.ent_bill_no.grid(row=1, column=1, padx=5, pady=5)

        tb.Label(entry_f, text="Date (DD-MM-YYYY):").grid(row=1, column=2, sticky=W, padx=5, pady=5)
        self.ent_bill_date = tb.Entry(entry_f, width=12)
        self.ent_bill_date.grid(row=1, column=3, padx=5, pady=5)
        self.ent_bill_date.insert(0, datetime.now().strftime("%d-%m-%Y"))

        tb.Label(entry_f, text="HSN Code:").grid(row=1, column=4, sticky=W, padx=5, pady=5)
        self.ent_hsn = tb.Entry(entry_f, width=12)
        self.ent_hsn.grid(row=1, column=5, padx=5, pady=5)

        tb.Label(entry_f, text="Item Name:").grid(row=1, column=6, sticky=W, padx=5, pady=5)
        self.ent_item = tb.Entry(entry_f, width=15)
        self.ent_item.grid(row=1, column=7, padx=5, pady=5)

        # Row 2: Financials & Action
        tb.Label(entry_f, text="Qty:").grid(row=2, column=0, sticky=W, padx=5, pady=5)
        self.ent_qty = tb.Entry(entry_f, width=12)
        self.ent_qty.grid(row=2, column=1, padx=5, pady=5)

        tb.Label(entry_f, text="Rate (₹):").grid(row=2, column=2, sticky=W, padx=5, pady=5)
        self.ent_rate = tb.Entry(entry_f, width=12)
        self.ent_rate.grid(row=2, column=3, padx=5, pady=5)

        tb.Label(entry_f, text="Tax (%):").grid(row=2, column=4, sticky=W, padx=5, pady=5)
        self.ent_tax_rate = tb.Entry(entry_f, width=12)
        self.ent_tax_rate.grid(row=2, column=5, padx=5, pady=5)
        self.ent_tax_rate.insert(0, "18")

        tb.Button(entry_f, text="💾 Save Sale", bootstyle="success", command=self.save_sale).grid(row=2, column=6, columnspan=2, padx=10, sticky=EW)

        # Sales Register Table
        table_f = tb.LabelFrame(self.tab_sales, text="Sales Register (Click a row to Print PDF, Edit, or Delete)", bootstyle="secondary", padding=10)
        table_f.pack(fill=BOTH, expand=True, padx=15, pady=5)
        
        cols = ("id", "bill_no", "date", "customer", "gstin", "pos", "taxable", "total")
        self.tree_sales = tb.Treeview(table_f, columns=cols, show="headings", bootstyle="info")
        self.tree_sales.heading("id", text="ID")
        self.tree_sales.heading("bill_no", text="Bill No")
        self.tree_sales.heading("date", text="Date")
        self.tree_sales.heading("customer", text="Customer Name")
        self.tree_sales.heading("gstin", text="GSTIN")
        self.tree_sales.heading("pos", text="POS")
        self.tree_sales.heading("taxable", text="Taxable (₹)")
        self.tree_sales.heading("total", text="Total (₹)")
        
        self.tree_sales.column("id", width=40, anchor=CENTER)
        for c in cols[1:]:
            self.tree_sales.column(c, width=100, anchor=CENTER)
        self.tree_sales.pack(fill=BOTH, expand=True, side=LEFT)

        # Action Toolbar
        action_btn_f = tb.Frame(table_f, padding=5)
        action_btn_f.pack(side=RIGHT, fill=Y, padx=5)
        tb.Button(action_btn_f, text="🖨️ PDF Invoice", bootstyle="info", command=self.print_sale_pdf).pack(fill=X, pady=5)
        tb.Button(action_btn_f, text="✏️ Edit Sale", bootstyle="warning", command=self.edit_sale).pack(fill=X, pady=5)
        tb.Button(action_btn_f, text="🗑️ Delete Sale", bootstyle="danger", command=self.delete_sale).pack(fill=X, pady=5)

        # Export Toolbar
        export_f = tb.Frame(self.tab_sales, padding=10)
        export_f.pack(fill=X, padx=15, pady=5)
        tb.Label(export_f, text="Month (MM):").pack(side=LEFT, padx=5)
        self.s_exp_month = tb.Combobox(export_f, width=5, state="readonly", values=[f"{m:02d}" for m in range(1, 13)])
        self.s_exp_month.pack(side=LEFT, padx=5)
        tb.Label(export_f, text="Year:").pack(side=LEFT, padx=5)
        self.s_exp_year = tb.Combobox(export_f, width=10, state="readonly")
        self.s_exp_year.pack(side=LEFT, padx=5)
        tb.Button(export_f, text="⚙️ Export GSTR-1 JSON (B2B, B2CL, B2CS, HSN)", bootstyle="primary", command=self.export_json).pack(side=RIGHT, padx=10)

    # ==========================================
    # TAB 2: PURCHASE REGISTER (ITC)
    # ==========================================
    def build_purchases_tab(self):
        entry_f = tb.LabelFrame(self.tab_purch, text="🛒 Enter Vendor Purchases (ITC)", bootstyle="warning", padding=15)
        entry_f.pack(fill=X, padx=15, pady=10)

        tb.Label(entry_f, text="Vendor Name:").grid(row=0, column=0, sticky=W, padx=5, pady=5)
        self.p_vendor_name = tb.Entry(entry_f, width=22)
        self.p_vendor_name.grid(row=0, column=1, padx=5, pady=5)

        tb.Label(entry_f, text="Vendor GSTIN:").grid(row=0, column=2, sticky=W, padx=5, pady=5)
        self.p_vendor_gstin = tb.Entry(entry_f, width=18)
        self.p_vendor_gstin.grid(row=0, column=3, padx=5, pady=5)

        tb.Label(entry_f, text="Bill No:").grid(row=0, column=4, sticky=W, padx=5, pady=5)
        self.p_bill_no = tb.Entry(entry_f, width=12)
        self.p_bill_no.grid(row=0, column=5, padx=5, pady=5)

        tb.Label(entry_f, text="Date (DD-MM-YYYY):").grid(row=0, column=6, sticky=W, padx=5, pady=5)
        self.p_bill_date = tb.Entry(entry_f, width=12)
        self.p_bill_date.grid(row=0, column=7, padx=5, pady=5)
        self.p_bill_date.insert(0, datetime.now().strftime("%d-%m-%Y"))

        tb.Label(entry_f, text="HSN Code:").grid(row=1, column=0, sticky=W, padx=5, pady=5)
        self.p_hsn = tb.Entry(entry_f, width=22)
        self.p_hsn.grid(row=1, column=1, padx=5, pady=5)

        tb.Label(entry_f, text="Item Name:").grid(row=1, column=2, sticky=W, padx=5, pady=5)
        self.p_item = tb.Entry(entry_f, width=18)
        self.p_item.grid(row=1, column=3, padx=5, pady=5)

        tb.Label(entry_f, text="Qty:").grid(row=1, column=4, sticky=W, padx=5, pady=5)
        self.p_qty = tb.Entry(entry_f, width=12)
        self.p_qty.grid(row=1, column=5, padx=5, pady=5)

        tb.Label(entry_f, text="Rate (₹):").grid(row=1, column=6, sticky=W, padx=5, pady=5)
        self.p_rate = tb.Entry(entry_f, width=12)
        self.p_rate.grid(row=1, column=7, padx=5, pady=5)

        tb.Label(entry_f, text="Tax (%):").grid(row=1, column=8, sticky=W, padx=5, pady=5)
        self.p_tax_rate = tb.Entry(entry_f, width=8)
        self.p_tax_rate.grid(row=1, column=9, padx=5, pady=5)
        self.p_tax_rate.insert(0, "18")

        tb.Button(entry_f, text="💾 Save Purchase", bootstyle="success", command=self.save_purchase).grid(row=1, column=10, padx=15)

        table_f = tb.LabelFrame(self.tab_purch, text="Purchase Register (Click a row to Edit or Delete)", bootstyle="secondary", padding=10)
        table_f.pack(fill=BOTH, expand=True, padx=15, pady=5)
        
        cols = ("id", "bill_no", "date", "vendor", "gstin", "taxable", "tax_credit", "total")
        self.tree_purch = tb.Treeview(table_f, columns=cols, show="headings", bootstyle="warning")
        self.tree_purch.heading("id", text="ID")
        self.tree_purch.heading("bill_no", text="Bill No")
        self.tree_purch.heading("date", text="Date")
        self.tree_purch.heading("vendor", text="Vendor Name")
        self.tree_purch.heading("gstin", text="GSTIN")
        self.tree_purch.heading("taxable", text="Taxable (₹)")
        self.tree_purch.heading("tax_credit", text="ITC Available (₹)")
        self.tree_purch.heading("total", text="Total (₹)")
        
        self.tree_purch.column("id", width=40, anchor=CENTER)
        for c in cols[1:]:
            self.tree_purch.column(c, width=100, anchor=CENTER)
        self.tree_purch.pack(fill=BOTH, expand=True, side=LEFT)

        p_action_f = tb.Frame(table_f, padding=5)
        p_action_f.pack(side=RIGHT, fill=Y, padx=5)
        tb.Button(p_action_f, text="✏️ Edit Purchase", bootstyle="warning", command=self.edit_purchase).pack(fill=X, pady=5)
        tb.Button(p_action_f, text="🗑️ Delete Purchase", bootstyle="danger", command=self.delete_purchase).pack(fill=X, pady=5)

    # ==========================================
    # TAB 3: GSTR-3B (MONTHLY SUMMARY)
    # ==========================================
    def build_gstr3b_tab(self):
        dash_f = tb.LabelFrame(self.tab_gstr3b, text="📊 GSTR-3B Monthly Liability Calculator", bootstyle="dark", padding=30)
        dash_f.pack(fill=X, padx=20, pady=30)
        
        filter_f = tb.Frame(dash_f)
        filter_f.pack(pady=10)
        tb.Label(filter_f, text="Select Month:").pack(side=LEFT, padx=5)
        self.dash_month = tb.Combobox(filter_f, width=8, state="readonly", values=[f"{m:02d}" for m in range(1, 13)])
        self.dash_month.pack(side=LEFT, padx=5)
        tb.Label(filter_f, text="Select Year:").pack(side=LEFT, padx=5)
        self.dash_year = tb.Combobox(filter_f, width=12, state="readonly")
        self.dash_year.pack(side=LEFT, padx=5)
        tb.Button(filter_f, text="🔄 Calculate Net Tax", bootstyle="primary", command=self.calculate_3b).pack(side=LEFT, padx=20)
        
        res_f = tb.Frame(dash_f)
        res_f.pack(pady=30)
        
        tb.Label(res_f, text="Total Output Tax (Sales):", font=("Helvetica", 13)).grid(row=0, column=0, sticky=E, pady=10)
        self.lbl_out_tax = tb.Label(res_f, text="₹ 0.00", font=("Helvetica", 14, "bold"), bootstyle="danger")
        self.lbl_out_tax.grid(row=0, column=1, sticky=W, padx=30)
        
        tb.Label(res_f, text="Minus Input Tax Credit (Purchases):", font=("Helvetica", 13)).grid(row=1, column=0, sticky=E, pady=10)
        self.lbl_in_tax = tb.Label(res_f, text="- ₹ 0.00", font=("Helvetica", 14, "bold"), bootstyle="success")
        self.lbl_in_tax.grid(row=1, column=1, sticky=W, padx=30)
        
        tb.Separator(res_f, orient=HORIZONTAL).grid(row=2, column=0, columnspan=2, sticky=EW, pady=15)
        
        tb.Label(res_f, text="Net Tax Payable to Govt:", font=("Helvetica", 16, "bold")).grid(row=3, column=0, sticky=E)
        self.lbl_net_tax = tb.Label(res_f, text="₹ 0.00", font=("Helvetica", 18, "bold"))
        self.lbl_net_tax.grid(row=3, column=1, sticky=W, padx=30)

    # ==========================================
    # CORE CALCULATION & VALIDATION UTILITIES
    # ==========================================
    def parse_and_validate_date(self, raw_date):
        """Strict calendar validation to eliminate impossible dates."""
        clean = raw_date.strip().replace('/', '-')
        dt = datetime.strptime(clean, "%d-%m-%Y")
        return dt.strftime("%d-%m-%Y"), str(dt.year), f"{dt.month:02d}"

    def compute_taxes(self, seller_state_code, pos_state_code, qty, rate, tax_rate):
        """Precision currency arithmetic using Decimal and ROUND_HALF_UP."""
        d_qty = Decimal(str(qty).strip() or "0")
        d_rate = Decimal(str(rate).strip() or "0")
        d_tax_rate = Decimal(str(tax_rate).strip() or "0")
        
        taxable = (d_qty * d_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        total_tax = (taxable * (d_tax_rate / Decimal('100'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        s_pos = str(seller_state_code).strip().zfill(2)
        c_pos = str(pos_state_code).strip().zfill(2)
        
        if s_pos == c_pos:
            cgst = (total_tax / Decimal('2')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            sgst = (total_tax - cgst).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            igst = Decimal('0.00')
        else:
            cgst = Decimal('0.00')
            sgst = Decimal('0.00')
            igst = total_tax
            
        total = taxable + cgst + sgst + igst
        return float(taxable), float(cgst), float(sgst), float(igst), float(total)

    # ==========================================
    # BUYER / CUSTOMER ACCOUNT HANDLERS
    # ==========================================
    def open_add_customer_window(self):
        popup = tb.Toplevel(self.root)
        popup.title("Register Buyer Profile")
        popup.geometry("450x320")
        popup.grab_set()

        tb.Label(popup, text="Buyer Full Name / Trade Name:").grid(row=0, column=0, padx=15, pady=10, sticky=W)
        ent_cname = tb.Entry(popup, width=28)
        ent_cname.grid(row=0, column=1, padx=10, pady=10)

        tb.Label(popup, text="Phone / Contact:").grid(row=1, column=0, padx=15, pady=10, sticky=W)
        ent_phone = tb.Entry(popup, width=28)
        ent_phone.grid(row=1, column=1, padx=10, pady=10)

        tb.Label(popup, text="Address:").grid(row=2, column=0, padx=15, pady=10, sticky=W)
        ent_caddr = tb.Entry(popup, width=28)
        ent_caddr.grid(row=2, column=1, padx=10, pady=10)

        tb.Label(popup, text="Buyer GSTIN (Leave blank for B2C):").grid(row=3, column=0, padx=15, pady=10, sticky=W)
        ent_cgstin = tb.Entry(popup, width=28)
        ent_cgstin.grid(row=3, column=1, padx=10, pady=10)

        tb.Label(popup, text="POS State Code (e.g. 24):").grid(row=4, column=0, padx=15, pady=10, sticky=W)
        ent_cpos = tb.Entry(popup, width=10)
        ent_cpos.grid(row=4, column=1, padx=10, pady=10, sticky=W)
        ent_cpos.insert(0, "24")

        def save_customer():
            name = ent_cname.get().strip()
            phone = ent_phone.get().strip()
            addr = ent_caddr.get().strip()
            gstin = ent_cgstin.get().strip().upper()
            pos = ent_cpos.get().strip()

            if not name:
                return messagebox.showerror("Missing Information", "Buyer Name is required.", parent=popup)

            if gstin and len(gstin) == 15:
                pos = gstin[:2]

            with self.conn:
                self.c.execute('''INSERT INTO customers (name, phone, address, gstin, state_code) 
                                  VALUES (?, ?, ?, ?, ?)
                                  ON CONFLICT(name) DO UPDATE SET phone=excluded.phone, address=excluded.address, 
                                  gstin=excluded.gstin, state_code=excluded.state_code''',
                               (name, phone, addr, gstin, pos))
            self.refresh_customer_list()
            self.combo_buyer_select.set(name)
            self.on_customer_selected(None)
            popup.destroy()
            messagebox.showinfo("Success", f"Buyer profile for '{name}' saved successfully!")

        tb.Button(popup, text="💾 Save Buyer Profile", bootstyle="success", command=save_customer).grid(row=5, column=0, columnspan=2, pady=15)

    def refresh_customer_list(self):
        self.c.execute("SELECT name FROM customers ORDER BY name ASC")
        self.combo_buyer_select['values'] = [r[0] for r in self.c.fetchall()]

    def on_customer_selected(self, event):
        buyer_name = self.combo_buyer_select.get()
        if buyer_name:
            self.c.execute("SELECT gstin, state_code FROM customers WHERE name=?", (buyer_name,))
            row = self.c.fetchone()
            if row:
                self.ent_customer_name.delete(0, END)
                self.ent_customer_name.insert(0, buyer_name)
                
                self.ent_customer_gstin.delete(0, END)
                if row[0]:
                    self.ent_customer_gstin.insert(0, row[0])
                
                self.ent_pos.delete(0, END)
                self.ent_pos.insert(0, row[1] if row[1] else "24")

    # ==========================================
    # PDF INVOICE GENERATOR (REPORTLAB)
    # ==========================================
    def print_sale_pdf(self):
        selected = self.tree_sales.selection()
        if not selected:
            return messagebox.showwarning("Selection Required", "Please select a sales invoice from the table to print/export PDF.")
        
        if not REPORTLAB_AVAILABLE:
            return messagebox.showerror(
                "Module Not Installed", 
                "The 'reportlab' package is required for PDF generation.\n\nPlease install it using:\npip install reportlab"
            )

        row_id = self.tree_sales.item(selected[0])['values'][0]
        self.c.execute("SELECT * FROM invoices WHERE id=?", (row_id,))
        rec = self.c.fetchone()
        if not rec:
            return

        self.c.execute("SELECT address FROM sellers WHERE name=?", (rec[1],))
        s_addr_row = self.c.fetchone()
        s_addr = s_addr_row[0] if s_addr_row else "Registered Office"

        self.c.execute("SELECT address, phone FROM customers WHERE name=?", (rec[3],))
        c_info = self.c.fetchone()
        c_addr = c_info[0] if c_info else "N/A"
        c_phone = c_info[1] if c_info else "N/A"

        default_filename = f"Invoice_{rec[6]}_{rec[3].replace(' ', '_')}.pdf"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Documents", "*.pdf")],
            initialfile=default_filename
        )
        if not file_path:
            return

        try:
            doc = SimpleDocTemplate(file_path, pagesize=A4, leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30)
            styles = getSampleStyleSheet()
            normal = styles["Normal"]
            
            title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, alignment=1, spaceAfter=15, textColor=colors.HexColor("#1A365D"))
            bold_style = ParagraphStyle('BoldStyle', parent=normal, fontName="Helvetica-Bold", fontSize=10)
            small_style = ParagraphStyle('SmallStyle', parent=normal, fontSize=9, leading=12)
            
            elements = []
            elements.append(Paragraph("<b>TAX INVOICE</b>", title_style))
            
            header_table_data = [
                [
                    Paragraph(f"<b>SUPPLIER (SELLER):</b><br/><b>{rec[1]}</b><br/>{s_addr}<br/><b>GSTIN:</b> {rec[2]}", small_style),
                    Paragraph(f"<b>Invoice No:</b> {rec[6]}<br/><b>Date:</b> {rec[7]}<br/><b>Place of Supply:</b> State {rec[5]}", small_style)
                ],
                [
                    Paragraph(f"<b>RECIPIENT (BUYER):</b><br/><b>{rec[3]}</b><br/>{c_addr}<br/><b>Phone:</b> {c_phone}<br/><b>GSTIN:</b> {rec[4]}", small_style),
                    Paragraph("<b>Original for Recipient</b><br/>Terms: Payment Due upon Receipt", small_style)
                ]
            ]
            t_head = Table(header_table_data, colWidths=[280, 255])
            t_head.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ('PADDING', (0, 0), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            elements.append(t_head)
            elements.append(Spacer(1, 15))

            item_data = [
                ["#", "Item Description", "HSN/SAC", "Qty", "Rate (₹)", "Taxable (₹)", "Tax %", "CGST (₹)", "SGST (₹)", "IGST (₹)", "Total (₹)"],
                ["1", rec[10], rec[9], f"{rec[11]:.2f}", f"{rec[12]:.2f}", f"{rec[13]:.2f}", f"{rec[14]:.1f}%", f"{rec[15]:.2f}", f"{rec[16]:.2f}", f"{rec[17]:.2f}", f"{rec[18]:.2f}"]
            ]
            t_items = Table(item_data, colWidths=[25, 110, 50, 35, 45, 60, 40, 45, 45, 45, 60])
            t_items.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (1, 1), (1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ('PADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(t_items)
            elements.append(Spacer(1, 15))

            summary_data = [
                ["Total Taxable Amount:", f"₹ {rec[13]:.2f}"],
                ["Central Tax (CGST):", f"₹ {rec[15]:.2f}"],
                ["State Tax (SGST):", f"₹ {rec[16]:.2f}"],
                ["Integrated Tax (IGST):", f"₹ {rec[17]:.2f}"],
                ["Total Invoice Value (INR):", f"₹ {rec[18]:.2f}"]
            ]
            t_summary = Table(summary_data, colWidths=[150, 100], hAlign='RIGHT')
            t_summary.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor("#0F172A")),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('PADDING', (0, 0), (-1, -1), 3),
            ]))
            elements.append(t_summary)
            elements.append(Spacer(1, 40))

            sign_data = [
                [Paragraph("<b>Declaration:</b><br/>We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct.", small_style),
                 Paragraph(f"For <b>{rec[1]}</b><br/><br/><br/><b>Authorized Signatory</b>", ParagraphStyle('RAlign', parent=small_style, alignment=2))]
            ]
            t_sign = Table(sign_data, colWidths=[330, 205])
            t_sign.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('PADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(t_sign)

            doc.build(elements)
            messagebox.showinfo("PDF Created", f"Tax invoice saved successfully to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Failed", f"An error occurred while generating PDF: {str(e)}")

    # ==========================================
    # EDIT & DELETE HANDLERS
    # ==========================================
    def delete_sale(self):
        selected = self.tree_sales.selection()
        if not selected:
            return messagebox.showwarning("Selection Required", "Please select a sales invoice from the table to delete.")
        
        row_id = self.tree_sales.item(selected[0])['values'][0]
        if messagebox.askyesno("Confirm Deletion", f"Are you sure you want to permanently delete Invoice ID #{row_id}?"):
            with self.conn:
                self.c.execute("DELETE FROM invoices WHERE id=?", (row_id,))
            self.refresh_year_list()
            self.load_all_data()
            messagebox.showinfo("Deleted", "Invoice deleted successfully.")

    def edit_sale(self):
        selected = self.tree_sales.selection()
        if not selected:
            return messagebox.showwarning("Selection Required", "Please select a sales invoice from the table to edit.")
        
        row_id = self.tree_sales.item(selected[0])['values'][0]
        self.c.execute("SELECT * FROM invoices WHERE id=?", (row_id,))
        record = self.c.fetchone()
        if not record:
            return

        edit_win = tb.Toplevel(self.root)
        edit_win.title(f"Edit Sale - Bill #{record[6]}")
        edit_win.geometry("500x520")
        edit_win.grab_set()

        fields = [
            ("Customer Name:", record[3]),
            ("Customer GSTIN:", record[4] if record[4] != "B2C_SALE" else ""),
            ("POS Code:", record[5]),
            ("Bill No:", record[6]),
            ("Date (DD-MM-YYYY):", record[7]),
            ("HSN Code:", record[9]),
            ("Item Name:", record[10]),
            ("Quantity:", record[11]),
            ("Rate (₹):", record[12]),
            ("Tax Rate (%):", record[14])
        ]
        
        entries = {}
        for i, (label, val) in enumerate(fields):
            tb.Label(edit_win, text=label).grid(row=i, column=0, padx=15, pady=5, sticky=W)
            ent = tb.Entry(edit_win, width=25)
            ent.grid(row=i, column=1, padx=15, pady=5)
            ent.insert(0, str(val))
            entries[label] = ent

        def update():
            try:
                b_date, b_year, _ = self.parse_and_validate_date(entries["Date (DD-MM-YYYY):"].get())
            except ValueError:
                return messagebox.showerror("Invalid Date", "Enter a valid calendar date in DD-MM-YYYY format.", parent=edit_win)
            
            try:
                c_gstin = entries["Customer GSTIN:"].get().strip().upper()
                pos = entries["POS Code:"].get().strip()
                if len(c_gstin) != 15:
                    c_gstin = "B2C_SALE"
                else:
                    pos = c_gstin[:2]

                s_gstin = record[2]
                taxable, cgst, sgst, igst, total = self.compute_taxes(
                    s_gstin[:2], pos, entries["Quantity:"].get(), entries["Rate (₹):"].get(), entries["Tax Rate (%):"].get()
                )

                with self.conn:
                    self.c.execute('''UPDATE invoices SET 
                                      customer_name=?, customer_gstin=?, pos=?, bill_no=?, bill_date=?, bill_year=?,
                                      hsn_code=?, item_name=?, qty=?, rate=?, taxable_val=?, tax_rate=?, cgst=?, sgst=?, igst=?, total_amount=?
                                      WHERE id=?''',
                                   (entries["Customer Name:"].get().strip(), c_gstin, pos, entries["Bill No:"].get().strip(),
                                    b_date, b_year, entries["HSN Code:"].get().strip(), entries["Item Name:"].get().strip(),
                                    entries["Quantity:"].get().strip(), entries["Rate (₹):"].get().strip(), taxable,
                                    entries["Tax Rate (%):"].get().strip(), cgst, sgst, igst, total, row_id))
                self.refresh_year_list()
                self.load_all_data()
                edit_win.destroy()
                messagebox.showinfo("Success", "Invoice updated successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update: {str(e)}", parent=edit_win)

        tb.Button(edit_win, text="💾 Update Invoice", bootstyle="success", command=update).grid(row=len(fields), column=0, columnspan=2, pady=15)

    def delete_purchase(self):
        selected = self.tree_purch.selection()
        if not selected:
            return messagebox.showwarning("Selection Required", "Please select a purchase record from the table to delete.")
        
        row_id = self.tree_purch.item(selected[0])['values'][0]
        if messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete Purchase ID #{row_id}?"):
            with self.conn:
                self.c.execute("DELETE FROM purchases WHERE id=?", (row_id,))
            self.refresh_year_list()
            self.load_all_data()
            messagebox.showinfo("Deleted", "Purchase record deleted successfully.")

    def edit_purchase(self):
        selected = self.tree_purch.selection()
        if not selected:
            return messagebox.showwarning("Selection Required", "Please select a purchase record from the table to edit.")
        
        row_id = self.tree_purch.item(selected[0])['values'][0]
        self.c.execute("SELECT * FROM purchases WHERE id=?", (row_id,))
        record = self.c.fetchone()
        if not record:
            return

        edit_win = tb.Toplevel(self.root)
        edit_win.title(f"Edit Purchase - Bill #{record[5]}")
        edit_win.geometry("500x480")
        edit_win.grab_set()

        fields = [
            ("Vendor Name:", record[3]),
            ("Vendor GSTIN:", record[4]),
            ("Bill No:", record[5]),
            ("Date (DD-MM-YYYY):", record[6]),
            ("HSN Code:", record[8]),
            ("Item Name:", record[9]),
            ("Quantity:", record[10]),
            ("Rate (₹):", record[11]),
            ("Tax Rate (%):", record[13])
        ]
        
        entries = {}
        for i, (label, val) in enumerate(fields):
            tb.Label(edit_win, text=label).grid(row=i, column=0, padx=15, pady=5, sticky=W)
            ent = tb.Entry(edit_win, width=25)
            ent.grid(row=i, column=1, padx=15, pady=5)
            ent.insert(0, str(val))
            entries[label] = ent

        def update():
            try:
                b_date, b_year, _ = self.parse_and_validate_date(entries["Date (DD-MM-YYYY):"].get())
            except ValueError:
                return messagebox.showerror("Invalid Date", "Enter a valid calendar date in DD-MM-YYYY format.", parent=edit_win)
            
            try:
                v_gstin = entries["Vendor GSTIN:"].get().strip().upper()
                s_gstin = record[2]
                pos = v_gstin[:2] if len(v_gstin) >= 2 else s_gstin[:2]

                taxable, cgst, sgst, igst, total = self.compute_taxes(
                    s_gstin[:2], pos, entries["Quantity:"].get(), entries["Rate (₹):"].get(), entries["Tax Rate (%):"].get()
                )

                with self.conn:
                    self.c.execute('''UPDATE purchases SET 
                                      vendor_name=?, vendor_gstin=?, bill_no=?, bill_date=?, bill_year=?,
                                      hsn_code=?, item_name=?, qty=?, rate=?, taxable_val=?, tax_rate=?, cgst=?, sgst=?, igst=?, total_amount=?
                                      WHERE id=?''',
                                   (entries["Vendor Name:"].get().strip(), v_gstin, entries["Bill No:"].get().strip(),
                                    b_date, b_year, entries["HSN Code:"].get().strip(), entries["Item Name:"].get().strip(),
                                    entries["Quantity:"].get().strip(), entries["Rate (₹):"].get().strip(), taxable,
                                    entries["Tax Rate (%):"].get().strip(), cgst, sgst, igst, total, row_id))
                self.refresh_year_list()
                self.load_all_data()
                edit_win.destroy()
                messagebox.showinfo("Success", "Purchase updated successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update: {str(e)}", parent=edit_win)

        tb.Button(edit_win, text="💾 Update Purchase", bootstyle="success", command=update).grid(row=len(fields), column=0, columnspan=2, pady=15)

    # ==========================================
    # LOGIC & DATABASE HANDLERS
    # ==========================================
    def open_add_seller_window(self):
        popup = tb.Toplevel(self.root)
        popup.title("Register New Taxpayer")
        popup.geometry("400x250") 
        popup.grab_set() 
        
        tb.Label(popup, text="Client Name:").grid(row=0, column=0, padx=15, pady=15, sticky=W)
        ent_name = tb.Entry(popup, width=30)
        ent_name.grid(row=0, column=1)
        
        tb.Label(popup, text="Registered Address:").grid(row=1, column=0, padx=15, pady=5, sticky=W)
        ent_address = tb.Entry(popup, width=30)
        ent_address.grid(row=1, column=1)
        
        tb.Label(popup, text="Client GSTIN:").grid(row=2, column=0, padx=15, pady=15, sticky=W)
        ent_gstin = tb.Entry(popup, width=30)
        ent_gstin.grid(row=2, column=1)
        
        def save():
            name = ent_name.get().strip()
            address = ent_address.get().strip()
            gstin = ent_gstin.get().strip().upper()
            
            if name and gstin:
                with self.conn:
                    self.c.execute('''INSERT INTO sellers (name, address, gstin) VALUES (?, ?, ?) 
                                      ON CONFLICT(name) DO UPDATE SET address=excluded.address, gstin=excluded.gstin''', 
                                   (name, address, gstin))
                self.refresh_seller_list()
                self.combo_seller_select.set(name)
                self.on_seller_selected(None)
                popup.destroy()
            else:
                messagebox.showerror("Error", "Name and GSTIN are required fields.", parent=popup)
                
        tb.Button(popup, text="💾 Save Client Profile", bootstyle="success", command=save).grid(row=3, column=0, columnspan=2, pady=10)

    def refresh_seller_list(self):
        self.c.execute("SELECT name FROM sellers ORDER BY name ASC")
        self.combo_seller_select['values'] = [r[0] for r in self.c.fetchall()]

    def refresh_year_list(self):
        self.c.execute("SELECT DISTINCT bill_year FROM invoices UNION SELECT DISTINCT bill_year FROM purchases")
        years = [r[0] for r in self.c.fetchall() if r[0]]
        self.s_exp_year['values'] = years
        self.dash_year['values'] = years
        if years:
            if not self.s_exp_year.get():
                self.s_exp_year.set(years[0])
            if not self.dash_year.get():
                self.dash_year.set(years[0])

    def on_seller_selected(self, event):
        sel = self.combo_seller_select.get()
        if sel:
            self.c.execute("SELECT gstin FROM sellers WHERE name=?", (sel,))
            self.lbl_active_gstin.config(text=self.c.fetchone()[0], bootstyle="success")
            self.load_all_data()

    def load_all_data(self):
        sel = self.combo_seller_select.get()
        if not sel:
            return
        
        for r in self.tree_sales.get_children():
            self.tree_sales.delete(r)
        self.c.execute("SELECT id, bill_no, bill_date, customer_name, customer_gstin, pos, taxable_val, total_amount FROM invoices WHERE seller_name=? ORDER BY id DESC", (sel,))
        for r in self.c.fetchall():
            self.tree_sales.insert("", END, values=(r[0], r[1], r[2], r[3], r[4], r[5], f"{r[6]:.2f}", f"{r[7]:.2f}"))
            
        for r in self.tree_purch.get_children():
            self.tree_purch.delete(r)
        self.c.execute("SELECT id, bill_no, bill_date, vendor_name, vendor_gstin, taxable_val, cgst+sgst+igst, total_amount FROM purchases WHERE seller_name=? ORDER BY id DESC", (sel,))
        for r in self.c.fetchall():
            self.tree_purch.insert("", END, values=(r[0], r[1], r[2], r[3], r[4], f"{r[5]:.2f}", f"{r[6]:.2f}", f"{r[7]:.2f}"))

    def save_sale(self):
        s_name, s_gstin = self.combo_seller_select.get(), self.lbl_active_gstin.cget("text")
        if not s_name or s_gstin == "[Not Selected]":
            return messagebox.showerror("Error", "Select Client first!")
        
        try:
            b_date, b_year, _ = self.parse_and_validate_date(self.ent_bill_date.get())
        except ValueError:
            return messagebox.showerror("Format Error", "Date must be a valid calendar date formatted strictly as DD-MM-YYYY.")
            
        try:
            c_gstin = self.ent_customer_gstin.get().strip().upper()
            pos = self.ent_pos.get().strip()
            
            if len(c_gstin) != 15:
                c_gstin = "B2C_SALE"
            else:
                pos = c_gstin[:2]
            
            taxable, cgst, sgst, igst, total = self.compute_taxes(
                s_gstin[:2], pos, self.ent_qty.get(), self.ent_rate.get(), self.ent_tax_rate.get()
            )
            
            with self.conn:
                self.c.execute('''INSERT INTO invoices 
                                  (seller_name, seller_gstin, customer_name, customer_gstin, pos, bill_no, bill_date, bill_year,
                                   hsn_code, item_name, qty, rate, taxable_val, tax_rate, cgst, sgst, igst, total_amount)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                               (s_name, s_gstin, self.ent_customer_name.get().strip(), c_gstin, pos, self.ent_bill_no.get().strip(), 
                                b_date, b_year, self.ent_hsn.get().strip(), self.ent_item.get().strip(), self.ent_qty.get().strip(), self.ent_rate.get().strip(), 
                                taxable, self.ent_tax_rate.get().strip(), cgst, sgst, igst, total))
            self.refresh_year_list()
            self.load_all_data()
            messagebox.showinfo("Success", "Sale Saved successfully!")
        except Exception as e:
            messagebox.showerror("Calculation Error", f"Check numeric inputs: {str(e)}")

    def save_purchase(self):
        s_name, s_gstin = self.combo_seller_select.get(), self.lbl_active_gstin.cget("text")
        if not s_name or s_gstin == "[Not Selected]":
            return messagebox.showerror("Error", "Select Client first!")
        
        try:
            b_date, b_year, _ = self.parse_and_validate_date(self.p_bill_date.get())
        except ValueError:
            return messagebox.showerror("Format Error", "Date must be a valid calendar date formatted strictly as DD-MM-YYYY.")
            
        try:
            v_gstin = self.p_vendor_gstin.get().strip().upper()
            pos = v_gstin[:2] if len(v_gstin) >= 2 else s_gstin[:2]
            
            taxable, cgst, sgst, igst, total = self.compute_taxes(
                s_gstin[:2], pos, self.p_qty.get(), self.p_rate.get(), self.p_tax_rate.get()
            )
            
            with self.conn:
                self.c.execute('''INSERT INTO purchases 
                                  (seller_name, seller_gstin, vendor_name, vendor_gstin, bill_no, bill_date, bill_year,
                                   hsn_code, item_name, qty, rate, taxable_val, tax_rate, cgst, sgst, igst, total_amount)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                               (s_name, s_gstin, self.p_vendor_name.get().strip(), v_gstin, self.p_bill_no.get().strip(), 
                                b_date, b_year, self.p_hsn.get().strip(), self.p_item.get().strip(), self.p_qty.get().strip(), self.p_rate.get().strip(), 
                                taxable, self.p_tax_rate.get().strip(), cgst, sgst, igst, total))
            self.refresh_year_list()
            self.load_all_data()
            messagebox.showinfo("Success", "Purchase Saved successfully!")
        except Exception as e:
            messagebox.showerror("Calculation Error", f"Check numeric inputs: {str(e)}")

    def calculate_3b(self):
        s_name = self.combo_seller_select.get()
        month, year = self.dash_month.get(), self.dash_year.get()
        if not s_name or not month or not year:
            return messagebox.showwarning("Missing", "Select client, month, and year.")
        
        self.c.execute("SELECT bill_date, cgst, sgst, igst FROM invoices WHERE seller_name=? AND bill_year=?", (s_name, year))
        out_tax = sum(Decimal(str(r[1])) + Decimal(str(r[2])) + Decimal(str(r[3])) for r in self.c.fetchall() if r[0].split('-')[1] == month)
        
        self.c.execute("SELECT bill_date, cgst, sgst, igst FROM purchases WHERE seller_name=? AND bill_year=?", (s_name, year))
        in_tax = sum(Decimal(str(r[1])) + Decimal(str(r[2])) + Decimal(str(r[3])) for r in self.c.fetchall() if r[0].split('-')[1] == month)
        
        net = out_tax - in_tax
        
        self.lbl_out_tax.config(text=f"₹ {float(out_tax):,.2f}")
        self.lbl_in_tax.config(text=f"- ₹ {float(in_tax):,.2f}")
        self.lbl_net_tax.config(text=f"₹ {float(net):,.2f}", bootstyle="danger" if net > Decimal('0.00') else "success")

    def backup_database(self, show_message=True):
        backup_dir = os.path.join(self.app_dir, "TaxVault_Backups")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"backup_{timestamp}.db")

        dest = sqlite3.connect(backup_path)
        try:
            self.conn.backup(dest)
        finally:
            dest.close()

        if show_message:
            messagebox.showinfo("Backup Complete", f"Database backup created at:\n{backup_path}")
        return backup_path

    # ==========================================
    # ADVANCED GSTR-1 JSON EXPORT (B2B, B2CL, B2CS, HSN)
    # ==========================================
    def export_json(self):
        s_gstin, s_name = self.lbl_active_gstin.cget("text"), self.combo_seller_select.get()
        month, year = self.s_exp_month.get(), self.s_exp_year.get()
        
        if not s_name or s_gstin == "[Not Selected]":
            return messagebox.showwarning("Missing Client", "Please select an Active Client at the top header first.")
        if not month:
            return messagebox.showwarning("Missing Month", "Please select an export Month (MM) at the bottom.")
        if not year:
            return messagebox.showwarning("Missing Year", "Please select an export Year at the bottom.")
        
        self.c.execute("SELECT * FROM invoices WHERE seller_name=? AND bill_year=?", (s_name, year))
        valid_rows = [r for r in self.c.fetchall() if r[7].split('-')[1] == month]
        if not valid_rows: 
            return messagebox.showwarning("No Data", f"No sales invoices found for client '{s_name}' in period {month}-{year}.")

        payload = {"gstin": s_gstin, "fp": f"{month}{year}", "version": "GST3.2.0", "b2b": []}
        
        b2b_invoices = {}
        b2cl_invoices = {} 
        b2cs_summary = {}
        hsn_summary = {}
        seller_pos = s_gstin[:2]
        
        for r in valid_rows:
            cust_gstin = r[4]
            pos = str(r[5]).zfill(2)
            inum = r[6]
            idt = r[7]
            qty = Decimal(str(r[11]))
            taxable = Decimal(str(r[13]))
            tax_rate = Decimal(str(r[14]))
            cgst = Decimal(str(r[15]))
            sgst = Decimal(str(r[16]))
            igst = Decimal(str(r[17]))
            total_amt = Decimal(str(r[18]))
            hsn_code = str(r[9]).strip()
            
            # Unregistered Sale (B2C) Routing: B2CL vs B2CS
            if cust_gstin == "B2C_SALE":
                if pos != seller_pos and total_amt > Decimal('250000.00'):
                    b2cl_invoices.setdefault(pos, []).append({
                        "inum": inum,
                        "idt": idt,
                        "val": float(total_amt),
                        "itms": [{
                            "num": 1,
                            "itm_det": {
                                "rt": float(tax_rate),
                                "txval": float(taxable),
                                "iamt": float(igst),
                                "csamt": 0.0
                            }
                        }]
                    })
                else:
                    key = (pos, float(tax_rate))
                    if key not in b2cs_summary:
                        b2cs_summary[key] = {"txval": Decimal('0.00'), "camt": Decimal('0.00'), "samt": Decimal('0.00'), "iamt": Decimal('0.00')}
                    b2cs_summary[key]["txval"] += taxable
                    b2cs_summary[key]["camt"] += cgst
                    b2cs_summary[key]["samt"] += sgst
                    b2cs_summary[key]["iamt"] += igst
            else:
                inv_key = (cust_gstin, inum)
                if inv_key not in b2b_invoices:
                    b2b_invoices[inv_key] = {
                        "idt": idt,
                        "val": Decimal('0.00'),
                        "pos": pos,
                        "rchrg": "N",
                        "inv_typ": "R",
                        "itms": []
                    }
                
                b2b_invoices[inv_key]["val"] += total_amt
                item_num = len(b2b_invoices[inv_key]["itms"]) + 1
                b2b_invoices[inv_key]["itms"].append({
                    "num": item_num, 
                    "itm_det": {
                        "rt": float(tax_rate),
                        "txval": float(taxable),
                        "cgst": float(cgst),
                        "sgst": float(sgst),
                        "igst": float(igst)
                    }
                })
            
            if hsn_code:
                if hsn_code not in hsn_summary:
                    hsn_summary[hsn_code] = {"qty": Decimal('0.00'), "val": Decimal('0.00'), "txval": Decimal('0.00'), "iamt": Decimal('0.00'), "camt": Decimal('0.00'), "samt": Decimal('0.00')}
                hsn_summary[hsn_code]["qty"] += qty
                hsn_summary[hsn_code]["val"] += total_amt
                hsn_summary[hsn_code]["txval"] += taxable
                hsn_summary[hsn_code]["camt"] += cgst
                hsn_summary[hsn_code]["samt"] += sgst
                hsn_summary[hsn_code]["iamt"] += igst

        customers = {}
        for (c_gstin, inv_num), inv_data in b2b_invoices.items():
            inv_data["val"] = float(inv_data["val"])
            final_invoice = {"inum": inv_num, **inv_data}
            customers.setdefault(c_gstin, []).append(final_invoice)
            
        for c_gstin, inv_list in customers.items(): 
            payload["b2b"].append({"ctin": c_gstin, "inv": inv_list})

        if b2cl_invoices:
            payload["b2cl"] = []
            for pos_code, inv_list in b2cl_invoices.items():
                payload["b2cl"].append({"pos": pos_code, "inv": inv_list})
            
        if b2cs_summary:
            payload["b2cs"] = []
            for (p_code, t_rate), data in b2cs_summary.items():
                sply_ty = "INTRA" if p_code == seller_pos else "INTER"
                payload["b2cs"].append({
                    "rt": t_rate,
                    "sply_ty": sply_ty,
                    "typ": "OE",
                    "pos": p_code,
                    "txval": float(data["txval"]),
                    "iamt": float(data["iamt"]),
                    "camt": float(data["camt"]),
                    "samt": float(data["samt"]),
                    "csamt": 0.0
                })
        
        if hsn_summary:
            hsn_data = []
            for i, (code, data) in enumerate(hsn_summary.items(), start=1):
                hsn_data.append({
                    "num": i,
                    "hsn_sc": code,
                    "uqc": "OTH",
                    "qty": float(data["qty"]),
                    "val": float(data["val"]),
                    "txval": float(data["txval"]),
                    "iamt": float(data["iamt"]), 
                    "camt": float(data["camt"]),
                    "samt": float(data["samt"]),
                    "csamt": 0.0
                })
            payload["hsn"] = {"data": hsn_data}

        self.backup_database()

        default_name = f"GSTR1_{s_gstin}_{month}-{year}.json"
        filename = filedialog.asksaveasfilename(
            title="Save GSTR-1 JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile=default_name
        )
        if not filename:
            return

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)

        messagebox.showinfo(
            "Exported & Backed Up",
            f"GSTR-1 JSON saved successfully to:\n{os.path.abspath(filename)}"
            f"\n\nDatabase securely backed up to AppData."
        )


if __name__ == "__main__":
    app = tb.Window(themename="cosmo")
    app.withdraw()  # Keep dashboard hidden until login is authenticated

    def launch_app():
        app.deiconify()  # Reveal the main dashboard
        TaxVaultMasterERP(app)

    LoginWindow(app, on_success=launch_app)
    app.mainloop()