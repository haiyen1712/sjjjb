#!/usr/bin/env python3
"""
Server phục vụ ứng dụng AI Data Analytics Agent B2B - Trường Giang
Hỗ trợ serve file tĩnh + API POST /api/upload đọc mọi file CSV / XLSX / XLS bằng pandas & openpyxl
Chạy trên cổng 8000 (hoặc cổng truyền qua biến môi trường PORT)
"""
import base64
import http.server
import json
import os
import re
import socketserver
from email.parser import BytesParser
from email.policy import default as email_policy

import io
import pandas as pd


def parse_raw_file(raw_bytes: bytes, filename: str):
    """
    Đọc file CSV/XLSX/XLS nguyên bản bằng pandas.
    Hỗ trợ mọi trường hợp: file đầy đủ, file vượt nhiều cột (> 200 cột),
    file chỉ có tiêu đề, file chứa ký tự mẫu ('x'), file dòng trống hoặc file 0 bytes.
    Không báo lỗi ở Chặng 1 để chuyển toàn bộ dữ liệu sang Chặng 2 làm sạch & chuẩn hóa.
    """
    fn = filename.lower()
    df = None

    if fn.endswith(".csv") or fn.endswith(".txt"):
        for enc in ["utf-8-sig", "utf-8", "cp1258", "latin1"]:
            try:
                text = raw_bytes.decode(enc)
                lines = [ln for ln in text.splitlines() if ln.strip()]
                if not lines:
                    df = pd.DataFrame(columns=["Cột 1"])
                    break
                first_line = lines[0]
                if ";" in first_line and first_line.count(";") >= first_line.count(","):
                    sep = ";"
                elif "	" in first_line and first_line.count("	") >= first_line.count(","):
                    sep = "	"
                else:
                    sep = ","
                df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str)
                break
            except Exception:
                continue

        if df is None:
            try:
                text = raw_bytes.decode("utf-8", errors="ignore")
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                if lines:
                    sep = ";" if ";" in lines[0] else ","
                    cols = [c.strip() for c in lines[0].split(sep)]
                    recs = []
                    for row_str in lines[1:]:
                        vals = [v.strip() for v in row_str.split(sep)]
                        rec = {cols[i]: (vals[i] if i < len(vals) else "") for i in range(len(cols))}
                        recs.append(rec)
                    if not cols:
                        cols = ["Cột 1"]
                    if not recs:
                        recs = [{c: "" for c in cols}]
                    return cols, recs
                else:
                    return ["Cột 1"], [{"Cột 1": ""}]
            except Exception:
                return ["Cột 1"], [{"Cột 1": ""}]

    elif fn.endswith(".xlsx") or fn.endswith(".xls"):
        try:
            xls = pd.ExcelFile(io.BytesIO(raw_bytes))
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name, dtype=str)
                break
        except Exception:
            df = pd.DataFrame(columns=["Cột 1"])
    else:
        return ["Cột 1"], [{"Cột 1": ""}]

    if df is None:
        df = pd.DataFrame(columns=["Cột 1"])

    cols = []
    for i, c in enumerate(df.columns):
        c_str = str(c).strip()
        if not c_str or c_str.startswith("Unnamed:"):
            cols.append(f"Cột {i+1}")
        else:
            cols.append(c_str)
    df.columns = cols

    records = []
    for _, row in df.iterrows():
        rec = {}
        for c in cols:
            val = row.get(c, "")
            if pd.isna(val):
                rec[c] = ""
            else:
                rec[c] = str(val).strip()
        records.append(rec)

    # Nếu không có dòng nào (ví dụ file chỉ có dòng tiêu đề), tạo 1 dòng trống để Chặng 2 thẩm định
    if not records:
        records = [{c: "" for c in cols}]

    return cols, records

PORT = int(os.environ.get("PORT", 8000))


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def _parse_multipart(content_type: str, body: bytes):
    """Tách file tải lên từ multipart/form-data mà không phụ thuộc module cgi."""
    header_block = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
    msg = BytesParser(policy=email_policy).parsebytes(header_block + body)
    if msg.is_multipart():
        for part in msg.iter_parts():
            filename = part.get_filename()
            if filename:
                payload = part.get_payload(decode=True)
                return filename, payload
    return None, None


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def _send_json(self, status_code: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        if self.path.rstrip("/") == "/api/upload":
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                if content_len <= 0:
                    return self._send_json(400, {"ok": False, "error": "Không nhận được dữ liệu file."})

                body = self.rfile.read(content_len)
                ctype = self.headers.get("Content-Type", "")
                filename = None
                raw_bytes = None

                if "application/json" in ctype:
                    obj = json.loads(body.decode("utf-8"))
                    filename = obj.get("filename", "upload.xlsx")
                    b64 = obj.get("data_base64", "")
                    if "," in b64:
                        b64 = b64.split(",", 1)[1]
                    raw_bytes = base64.b64decode(b64)
                elif "multipart/form-data" in ctype:
                    filename, raw_bytes = _parse_multipart(ctype, body)
                else:
                    filename = self.headers.get("X-Filename", "upload.csv")
                    raw_bytes = body

                if raw_bytes is None:
                    raw_bytes = b""
                if not filename:
                    filename = "upload.csv" 

                cols, records = parse_raw_file(raw_bytes, filename)
                return self._send_json(200, {
                    "ok": True,
                    "filename": filename,
                    "columns": cols,
                    "total_rows": len(records),
                    "rows": records
                })
            except Exception as exc:
                return self._send_json(400, {"ok": False, "error": str(exc)})

        return self._send_json(404, {"ok": False, "error": "Endpoint không tồn tại."})


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with ReusableTCPServer(("", PORT), Handler) as httpd:
        print("==================================================================")
        print("  AI Data Analytics Agent B2B - Trường Giang")
        print(f"  Đang chạy tại: http://localhost:{PORT}")
        print("==================================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nĐang dừng server...")
            httpd.shutdown()
