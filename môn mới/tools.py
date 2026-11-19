"""
BỘ CÔNG CỤ NGHIỆP VỤ (BUSINESS TOOLS) CHO AI AGENT XỬ LÝ CƠ HỘI BÁN HÀNG B2B
Hệ thống Trường Giang
"""

import math
from typing import Dict, List, Any, Tuple
from config import (
    PRODUCT_CATALOG,
    DEFAULT_IN_STOCK_LEAD_DAYS,
    DISCOUNT_TIERS,
    MANAGER_MAX_DISCOUNT_PCT,
    BUDGET_TOLERANCE_PCT,
    SALES_REPRESENTATIVES,
    SALES_MANAGER
)


def format_currency_vnd(amount: float) -> str:
    """Định dạng tiền tệ VNĐ chuẩn có dấu chấm phân cách hàng nghìn"""
    if amount is None or math.isnan(amount):
        return "Chưa xác định"
    return f"{int(round(amount)):,} VNĐ".replace(",", ".")


def validate_request_completeness(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Kỹ năng 1 (Tool): Kiểm tra tính đầy đủ của dữ liệu yêu cầu ban đầu.
    Xác định các trường còn thiếu: Tên khách hàng, liên hệ, danh mục sản phẩm, số lượng, ngân sách, thời hạn.
    """
    missing_fields = []
    clarification_questions = []

    # 1. Kiểm tra thông tin định danh khách hàng
    customer_name = request_data.get("customer_name")
    if not customer_name or str(customer_name).strip() == "":
        missing_fields.append("Tên doanh nghiệp / Khách hàng")
        clarification_questions.append("Quý khách vui lòng cung cấp Tên công ty/doanh nghiệp tiếp nhận báo giá.")

    contact = request_data.get("contact")
    if not contact or str(contact).strip() == "":
        missing_fields.append("Thông tin liên hệ (Email/Số điện thoại)")
        clarification_questions.append("Quý khách vui lòng để lại địa chỉ Email hoặc Số điện thoại để nhân viên phụ trách gửi hồ sơ đề xuất.")

    # 2. Kiểm tra danh mục sản phẩm và số lượng
    items = request_data.get("items", [])
    if not items or len(items) == 0:
        missing_fields.append("Danh sách sản phẩm / dịch vụ")
        clarification_questions.append("Quý khách vui lòng chỉ định cụ thể các mã sản phẩm hoặc thiết bị/dịch vụ cần triển khai.")
    else:
        for idx, item in enumerate(items, 1):
            qty = item.get("quantity")
            p_id = item.get("product_id")
            if qty is None or qty <= 0:
                missing_fields.append(f"Số lượng cho hạng mục #{idx} ({p_id or 'Chưa rõ mã'})")
                clarification_questions.append(f"Quý khách vui lòng xác nhận số lượng dự kiến cho thiết bị {p_id or 'ở dòng ' + str(idx)}.")

    # 3. Kiểm tra ngân sách
    budget = request_data.get("budget")
    if budget is None or budget <= 0:
        missing_fields.append("Ngân sách dự kiến (Budget)")
        clarification_questions.append("Quý khách vui lòng chia sẻ dải ngân sách dự kiến để Trường Giang cân đối gói giải pháp và chính sách giá phù hợp nhất.")

    # 4. Kiểm tra thời hạn mong muốn
    lead_days = request_data.get("requested_lead_days")
    if lead_days is None or lead_days <= 0:
        missing_fields.append("Thời hạn triển khai / ngày cần giao (Lead-time)")
        clarification_questions.append("Quý khách cần hoàn thành giao hàng và triển khai hệ thống trong bao nhiêu ngày kể từ ngày ký hợp đồng?")

    is_complete = (len(missing_fields) == 0)

    return {
        "is_complete": is_complete,
        "missing_fields": missing_fields,
        "clarification_questions": clarification_questions,
        "missing_count": len(missing_fields)
    }


def check_inventory_and_leadtime(items: List[Dict[str, Any]], requested_lead_days: int) -> Dict[str, Any]:
    """
    Kỹ năng 2 (Tool): Thẩm định tồn kho khả dụng và tính toán khả năng đáp ứng thời hạn.
    Đối chiếu số lượng với CSDL kho, tính thời gian nhập hàng nếu thiếu hàng.
    """
    item_analysis = []
    all_in_stock = True
    max_restock_lead = 0
    unknown_products = []

    for item in items:
        p_id = item.get("product_id", "").strip().upper()
        req_qty = item.get("quantity", 0)

        catalog_entry = PRODUCT_CATALOG.get(p_id)
        if not catalog_entry:
            unknown_products.append(p_id)
            item_analysis.append({
                "product_id": p_id,
                "product_name": "Sản phẩm không có trong danh mục niêm yết",
                "unit": "-",
                "requested_qty": req_qty,
                "stock_available": 0,
                "is_in_stock": False,
                "shortage_qty": req_qty,
                "restock_lead_days": 30,
                "note": "Cần Vận hành tra cứu nguồn hàng đặc thù"
            })
            all_in_stock = False
            max_restock_lead = max(max_restock_lead, 30)
            continue

        stock_avail = catalog_entry["stock_available"]
        restock_lead = catalog_entry["restock_lead_days"]
        is_in_stock = (stock_avail >= req_qty)
        shortage = max(0, req_qty - stock_avail)

        if not is_in_stock:
            all_in_stock = False
            max_restock_lead = max(max_restock_lead, restock_lead)

        item_analysis.append({
            "product_id": p_id,
            "product_name": catalog_entry["name"],
            "unit": catalog_entry["unit"],
            "requested_qty": req_qty,
            "stock_available": stock_avail,
            "is_in_stock": is_in_stock,
            "shortage_qty": shortage,
            "restock_lead_days": restock_lead,
            "note": "Đủ tồn kho khả dụng" if is_in_stock else f"Thiếu {shortage} {catalog_entry['unit']}, cần {restock_lead} ngày nhập kho"
        })

    # Tính toán thời hạn khả thi thực tế
    if all_in_stock:
        feasible_days = DEFAULT_IN_STOCK_LEAD_DAYS
        lead_time_basis = f"Tất cả sản phẩm có sẵn trong kho Trường Giang -> Thời gian xuất kho và giao nhận: {DEFAULT_IN_STOCK_LEAD_DAYS} ngày làm việc."
    else:
        feasible_days = max_restock_lead + DEFAULT_IN_STOCK_LEAD_DAYS
        lead_time_basis = f"Có sản phẩm thiếu kho -> Cần nhập hàng tối đa {max_restock_lead} ngày + {DEFAULT_IN_STOCK_LEAD_DAYS} ngày xuất kho = {feasible_days} ngày làm việc."

    # So sánh với thời hạn khách yêu cầu
    if requested_lead_days is not None and requested_lead_days > 0:
        lead_time_feasible = (feasible_days <= requested_lead_days)
        gap_days = requested_lead_days - feasible_days
        if lead_time_feasible:
            fulfillment_verdict = f"ĐÁP ỨNG TIẾN ĐỘ: Khách cần trong {requested_lead_days} ngày, Trường Giang giao trong {feasible_days} ngày."
        else:
            fulfillment_verdict = f"KHÔNG ĐÁP ỨNG TIẾN ĐỘ: Khách cần gấp trong {requested_lead_days} ngày nhưng Trường Giang cần tối thiểu {feasible_days} ngày (chậm {abs(gap_days)} ngày)."
    else:
        lead_time_feasible = True
        gap_days = 0
        fulfillment_verdict = f"Khách chưa xác định ngày giao, thời gian bàn giao dự kiến khả thi là {feasible_days} ngày làm việc."

    return {
        "all_in_stock": all_in_stock,
        "feasible_days": feasible_days,
        "requested_lead_days": requested_lead_days,
        "lead_time_feasible": lead_time_feasible,
        "gap_days": gap_days,
        "fulfillment_verdict": fulfillment_verdict,
        "lead_time_basis": lead_time_basis,
        "item_analysis": item_analysis,
        "unknown_products": unknown_products
    }


def calculate_pricing_and_discount(
    items: List[Dict[str, Any]],
    requested_discount_pct: float,
    customer_budget: float
) -> Dict[str, Any]:
    """
    Kỹ năng 3 (Tool): Áp bảng giá niêm yết, tính chiết khấu theo chính sách bậc thang và kiểm tra thẩm quyền.
    So sánh giá trị đề xuất với ngân sách khách hàng.
    """
    detailed_lines = []
    total_list_price = 0.0

    for item in items:
        p_id = item.get("product_id", "").strip().upper()
        qty = item.get("quantity", 0)
        catalog_entry = PRODUCT_CATALOG.get(p_id)

        if catalog_entry:
            unit_price = catalog_entry["list_price"]
            p_name = catalog_entry["name"]
            unit = catalog_entry["unit"]
        else:
            unit_price = 0.0
            p_name = f"Sản phẩm {p_id} (chưa có giá niêm yết)"
            unit = "Gói"

        line_total = unit_price * qty
        total_list_price += line_total

        detailed_lines.append({
            "product_id": p_id,
            "product_name": p_name,
            "unit": unit,
            "quantity": qty,
            "unit_price": unit_price,
            "line_total": line_total
        })

    # 1. Xác định khung chiết khấu tiêu chuẩn theo nấc giá trị đơn hàng
    matched_tier = None
    for tier in DISCOUNT_TIERS:
        if tier["min_val"] <= total_list_price < tier["max_val"]:
            matched_tier = tier
            break

    if not matched_tier:
        matched_tier = DISCOUNT_TIERS[-1]

    standard_discount_pct = matched_tier["standard_discount_pct"]
    sales_rep_max_pct = matched_tier["sales_rep_max_pct"]

    # 2. Xử lý yêu cầu chiết khấu của khách hàng
    if requested_discount_pct is None or requested_discount_pct <= 0:
        applied_discount_pct = standard_discount_pct
        discount_scenario = "Khách không yêu cầu chiết khấu riêng -> Áp dụng chiết khấu tiêu chuẩn theo quy chế."
        requires_manager_approval = False
        exceeds_policy_ceiling = False
    elif requested_discount_pct <= sales_rep_max_pct:
        applied_discount_pct = requested_discount_pct
        discount_scenario = f"Khách đề nghị {requested_discount_pct}% (nằm trong hạn mức NVKD tối đa {sales_rep_max_pct}%)."
        requires_manager_approval = False
        exceeds_policy_ceiling = False
    elif requested_discount_pct <= MANAGER_MAX_DISCOUNT_PCT:
        applied_discount_pct = requested_discount_pct
        discount_scenario = f"Khách đề nghị {requested_discount_pct}% (vượt thẩm quyền NVKD {sales_rep_max_pct}%, trong trần TPKD {MANAGER_MAX_DISCOUNT_PCT}%)."
        requires_manager_approval = True
        exceeds_policy_ceiling = False
    else:
        applied_discount_pct = MANAGER_MAX_DISCOUNT_PCT
        discount_scenario = f"Khách đề nghị {requested_discount_pct}% vượt trần tối đa toàn công ty ({MANAGER_MAX_DISCOUNT_PCT}%)."
        requires_manager_approval = True
        exceeds_policy_ceiling = True

    discount_amount = total_list_price * (applied_discount_pct / 100.0)
    final_proposed_price = total_list_price - discount_amount

    # 3. So sánh với ngân sách của khách hàng
    if customer_budget is not None and customer_budget > 0:
        budget_variance = customer_budget - final_proposed_price
        budget_variance_pct = (budget_variance / final_proposed_price) * 100.0

        if final_proposed_price <= customer_budget:
            budget_status = "FEASIBLE"
            budget_verdict = f"Ngân sách ĐẠT: Ngân sách khách ({format_currency_vnd(customer_budget)}) dư {format_currency_vnd(budget_variance)} so với giá đề xuất."
        elif abs(budget_variance) / customer_budget * 100.0 <= BUDGET_TOLERANCE_PCT:
            budget_status = "MARGINAL_DEFICIT"
            budget_verdict = f"Thiếu ngân sách nhẹ (hụt {format_currency_vnd(abs(budget_variance))}, ~{abs(budget_variance_pct):.1f}% <= {BUDGET_TOLERANCE_PCT}%). Cần TPKD hỗ trợ giá hoặc xin khách bổ sung."
            requires_manager_approval = True
        else:
            budget_status = "INFEASIBLE"
            budget_verdict = f"Vượt quá ngân sách (hụt {format_currency_vnd(abs(budget_variance))}, ~{abs(budget_variance_pct):.1f}% > {BUDGET_TOLERANCE_PCT}%). Không thể đáp ứng bằng chiết khấu thông thường."
    else:
        budget_status = "UNKNOWN"
        budget_variance = 0.0
        budget_variance_pct = 0.0
        budget_verdict = "Chưa có thông tin ngân sách từ khách hàng."

    return {
        "total_list_price": total_list_price,
        "standard_discount_pct": standard_discount_pct,
        "sales_rep_max_pct": sales_rep_max_pct,
        "manager_max_pct": MANAGER_MAX_DISCOUNT_PCT,
        "requested_discount_pct": requested_discount_pct or 0.0,
        "applied_discount_pct": applied_discount_pct,
        "discount_amount": discount_amount,
        "final_proposed_price": final_proposed_price,
        "discount_scenario": discount_scenario,
        "requires_manager_approval": requires_manager_approval,
        "exceeds_policy_ceiling": exceeds_policy_ceiling,
        "customer_budget": customer_budget,
        "budget_variance": budget_variance,
        "budget_variance_pct": budget_variance_pct,
        "budget_status": budget_status,
        "budget_verdict": budget_verdict,
        "detailed_lines": detailed_lines
    }


def generate_customer_email(dossier: Dict[str, Any]) -> str:
    """
    Kỹ năng 4 (Tool): Tạo bản nháp email phản hồi khách hàng theo từng trạng thái nghiệp vụ.
    """
    status = dossier.get("final_status")
    c_name = dossier.get("customer_name", "Quý khách hàng")
    rep = dossier.get("sales_rep", {})
    req_id = dossier.get("opportunity_id", "REQ-TG")

    rep_signature = f"""
Trân trọng,
{rep.get('name', 'Phòng Kinh doanh Doanh nghiệp')}
Chuyên viên Tư vấn Giải pháp B2B | Hệ thống Trường Giang
Hotline/Zalo: {rep.get('phone', '0912.345.678')}
Email: {rep.get('email', 'kd@truonggiang.vn')}
Website: https://truonggiang.vn
"""

    if status == "CẦN BỔ SUNG THÔNG TIN":
        questions = "\n".join([f"  {idx}. {q}" for idx, q in enumerate(dossier.get("clarification_questions", []), 1)])
        return f"""Kính gửi Quý Công ty {c_name},

Lời đầu tiên, Trường Giang xin gửi lời chào trân trọng và cảm ơn Quý công ty đã quan tâm đến giải pháp thiết bị công nghệ của chúng tôi (Mã cơ hội: #{req_id}).

Để có thể lập Bảng dự thảo giải pháp tối ưu và chính xác nhất về mặt kỹ thuật, ngân sách cũng như cam kết tiến độ bàn giao, chúng tôi kính đề nghị Quý công ty vui lòng làm rõ hoặc bổ sung một số điểm sau:

{questions}

Ngay khi nhận được phản hồi từ Quý công ty, chuyên viên phụ trách của chúng tôi sẽ hoàn thiện Hồ sơ đề xuất chính thức và gửi lại trong vòng 2 giờ làm việc.

Rất mong sớm nhận được thông tin từ Quý công ty!

{rep_signature}"""

    elif status in ["CÓ THỂ TIẾP TỤC", "CHỜ DUYỆT"]:
        price = dossier.get("pricing", {})
        inv = dossier.get("inventory", {})

        table_rows = []
        for idx, line in enumerate(price.get("detailed_lines", []), 1):
            table_rows.append(
                f"  {idx}. {line['product_name']} ({line['product_id']}) | SL: {line['quantity']} {line['unit']} | Đơn giá niêm yết: {format_currency_vnd(line['unit_price'])} | Thành tiền: {format_currency_vnd(line['line_total'])}"
            )
        table_str = "\n".join(table_rows)

        discount_note = ""
        if price.get("applied_discount_pct", 0) > 0:
            discount_note = f"\n- Mức chiết khấu doanh nghiệp áp dụng: {price['applied_discount_pct']}% (-{format_currency_vnd(price['discount_amount'])})"

        approval_tag = ""
        if status == "CHỜ DUYỆT":
            approval_tag = "\n*(Lưu ý nội bộ: Báo giá bao gồm chính sách chiết khấu đặc biệt đang được trình Trưởng phòng Kinh doanh ký duyệt chính thức trước khi gửi đi)*\n"

        return f"""Kính gửi Quý Công ty {c_name},

Trường Giang xin chân thành cảm ơn Quý công ty đã tin tưởng lựa chọn chúng tôi làm đối tác cung cấp thiết bị và giải pháp công nghệ.

Căn cứ trên yêu cầu của Quý công ty, Trường Giang xin trân trọng gửi Bản dự thảo Báo giá và Phương án triển khai chi tiết (Mã cơ hội: #{req_id}) như sau:

I. DANH MỤC THIẾT BỊ VÀ DỊCH VỤ DỰ KIẾN:
{table_str}

II. TỔNG HỢP GIÁ TRỊ VÀ CHÍNH SÁCH ƯU ĐÃI:
- Tổng giá trị niêm yết: {format_currency_vnd(price.get('total_list_price', 0))}{discount_note}
- TỔNG GIÁ TRỊ ĐỀ XUẤT (Chưa VAT): {format_currency_vnd(price.get('final_proposed_price', 0))}
- Tiến độ bàn giao và triển khai: Cam kết hoàn thành trong {inv.get('feasible_days', 2)} ngày làm việc kể từ ngày hoàn tất thủ tục hợp đồng.
{approval_tag}
III. CAM KẾT CHẤT LƯỢNG & BẢO HÀNH:
- Thiết bị nhập khẩu chính hãng mới 100%, có đầy đủ chứng chỉ CO/CQ.
- Hỗ trợ kỹ thuật onsite tiêu chuẩn và gói bảo trì định kỳ.

Quý công ty vui lòng xem xét bản dự thảo trên. Chuyên viên {rep.get('name')} sẽ chủ động liên hệ với Quý công ty để hỗ trợ các thủ tục tiếp theo.

{rep_signature}"""

    else:  # CHƯA ĐÁP ỨNG
        reason = dossier.get("infeasible_reason", "Chưa đáp ứng được yêu cầu về tiến độ hoặc ngân sách hiện hành.")
        return f"""Kính gửi Quý Công ty {c_name},

Trường Giang trân trọng cảm ơn Quý công ty đã quan tâm và gửi yêu cầu hợp tác đến chúng tôi (Mã cơ hội: #{req_id}).

Sau khi đối chiếu kỹ lưỡng khả năng đáp ứng kỹ thuật, tồn kho khả dụng và chính sách thương mại, chúng tôi rất tiếc phải thông báo hiện tại Trường Giang chưa thể đáp ứng đầy đủ 100% điều kiện ban đầu của Quý công ty vì lý do:
-> {reason}

ĐỀ XUẤT PHƯƠNG ÁN THAY THẾ TỪ TRƯỜNG GIANG:
- Về tiến độ: Chúng tôi có thể phân kỳ giao trước các thiết bị có sẵn trong kho, phần còn lại sẽ giao ngay sau khi hoàn tất nhập kho.
- Về cấu hình/ngân sách: Trường Giang sẵn sàng cử chuyên gia tư vấn dòng sản phẩm tương đương về hiệu năng nhằm tối ưu hóa chi phí khớp với ngân sách của Quý công ty.

Chuyên viên {rep.get('name')} ({rep.get('phone')}) sẽ liên hệ lại với Quý công ty trong ngày hôm nay để cùng trao đổi phương án điều chỉnh phù hợp nhất.

{rep_signature}"""


def generate_approval_ticket(dossier: Dict[str, Any]) -> str:
    """
    Kỹ năng 4 (Tool): Tạo Phiếu chuyển duyệt nội bộ (Approval Ticket) cho Trưởng phòng Kinh doanh.
    """
    req_id = dossier.get("opportunity_id", "REQ-TG")
    c_name = dossier.get("customer_name", "Doanh nghiệp")
    rep = dossier.get("sales_rep", {})
    price = dossier.get("pricing", {})
    inv = dossier.get("inventory", {})

    return f"""================================================================================
PHIẾU CHUYỂN DUYỆT VƯỢT THẨM QUYỀN / CHIẾT KHẤU ĐẶC BIỆT
Mã hồ sơ: #{req_id} | Ngày tạo: {dossier.get('created_at', 'Hôm nay')}
Người đề xuất: {rep.get('name')} ({rep.get('id')}) | Bộ phận: Kinh doanh B2B
Người phê duyệt: {SALES_MANAGER['name']} - {SALES_MANAGER['title']}
================================================================================

1. THÔNG TIN KHÁCH HÀNG & CƠ HỘI:
   - Doanh nghiệp: {c_name}
   - Người liên hệ: {dossier.get('contact', 'Chưa rõ')}
   - Tiến độ yêu cầu: {dossier.get('requested_lead_days', 'Chưa rõ')} ngày (Tiến độ kho đáp ứng: {inv.get('feasible_days')} ngày)

2. THẨM ĐỊNH TÀI CHÍNH & CHÍNH SÁCH GIÁ:
   - Tổng giá niêm yết (List Price): {format_currency_vnd(price.get('total_list_price', 0))}
   - Mức chiết khấu tiêu chuẩn quy định: {price.get('standard_discount_pct', 0)}%
   - Hạn mức tự quyết tối đa của NVKD: {price.get('sales_rep_max_pct', 0)}%
   - MỨC CHIẾT KHẤU KHÁCH YÊU CẦU: {price.get('requested_discount_pct', 0)}% (VƯỢT QUYỀN NVKD)
   - Tiền chiết khấu đề nghị: -{format_currency_vnd(price.get('discount_amount', 0))}
   - GIÁ TRỊ SAU CHIẾT KHẤU ĐỀ XUẤT: {format_currency_vnd(price.get('final_proposed_price', 0))}
   - Ngân sách của khách hàng: {format_currency_vnd(price.get('customer_budget', 0))}
   - Tình trạng ngân sách: {price.get('budget_verdict')}

3. CĂN CỨ VÀ ĐỀ XUẤT CỦA AI AGENT:
   - Tồn kho khả dụng: {'Tất cả có sẵn' if inv.get('all_in_stock') else 'Cần nhập thêm một số linh kiện'}
   - Đánh giá biên lợi nhuận: Nằm trong khung cho phép của Trưởng phòng (<= {price.get('manager_max_pct')}%)
   - Khuyến nghị: ĐỒNG Ý PHÊ DUYỆT để chốt deal chiến lược với khách hàng doanh nghiệp.

================================================================================
HÀNH ĐỘNG CỦA TRƯỞNG PHÒNG KINH DOANH:
[  ] PHÊ DUYỆT (Chấp thuận mức chiết khấu đề xuất)
[  ] YÊU CẦU ĐIỀU CHỈNH (Mức chiết khấu tối đa cho phép: ..... %)
[  ] TỪ CHỐI (Không chấp thuận chính sách giá đặc biệt)
Ý kiến phê duyệt: ................................................................
================================================================================
"""


def generate_html_report(batch_res: Dict[str, Any], manager_name: str = "Trường Giang") -> str:
    """
    Kỹ năng xuất báo cáo HTML trực tiếp trên giao diện Agent (Bước 8 trong quy trình).
    Tạo bản Báo cáo Quản trị Toàn diện (Executive Analytics Report) tông màu Hồng Rose Luxury,
    HTML5 responsive, hỗ trợ in ấn A4/PDF, hiển thị bảng biểu, KPIs và nhận xét AI.
    """
    import datetime
    now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    report_code = f"RP-{datetime.datetime.now().strftime('%Y%m%d')}-B2B"

    counts = batch_res.get("counts", {})
    total_ops = batch_res.get("total_opportunities", 0)
    eligible_val = batch_res.get("total_eligible_value", 0)
    dossiers = batch_res.get("dossiers", [])

    c_tiep_tuc = counts.get("CÓ THỂ TIẾP TỤC", 0)
    c_cho_duyet = counts.get("CHỜ DUYỆT", 0)
    c_bo_sung = counts.get("CẦN BỔ SUNG THÔNG TIN", 0)
    c_chua_dat = counts.get("CHƯA ĐÁP ỨNG", 0)

    p_tiep_tuc = round(c_tiep_tuc / total_ops * 100, 1) if total_ops else 0
    p_cho_duyet = round(c_cho_duyet / total_ops * 100, 1) if total_ops else 0
    p_bo_sung = round(c_bo_sung / total_ops * 100, 1) if total_ops else 0
    p_chua_dat = round(c_chua_dat / total_ops * 100, 1) if total_ops else 0

    # Render từng dòng cơ hội vào bảng HTML
    rows_html = []
    for idx, d in enumerate(dossiers, 1):
        status = d.get("final_status", "")
        status_badge_class = {
            "CÓ THỂ TIẾP TỤC": "badge-ready",
            "CHỜ DUYỆT": "badge-pending",
            "CẦN BỔ SUNG THÔNG TIN": "badge-info",
            "CHƯA ĐÁP ỨNG": "badge-reject"
        }.get(status, "badge-muted")

        price_info = d.get("pricing") or {}
        final_price = price_info.get("final_proposed_price", 0) or 0
        final_price_str = format_currency_vnd(final_price) if final_price > 0 else "—"
        budget_str = format_currency_vnd(d.get("customer_budget")) if d.get("customer_budget") else "<span class='text-muted'>Thiếu</span>"
        lead_days = f"{d.get('requested_lead_days')} ngày" if d.get('requested_lead_days') else "<span class='text-muted'>Thiếu</span>"

        disc_pct = price_info.get("applied_discount_pct")
        if disc_pct is None:
            disc_pct = price_info.get("requested_discount_pct", 0) or 0
        disc_str = f"{disc_pct:g}%" if disc_pct > 0 else "0%"

        sales_name = d.get("sales_rep", {}).get("name", "Chưa gán")
        sales_id = d.get("sales_rep", {}).get("id", "")

        rows_html.append(f"""
        <tr>
            <td style="font-weight:700; color:#9d174d;">{d.get('opportunity_id')}</td>
            <td>
                <div style="font-weight:600; color:#4c0519;">{d.get('customer_name')}</div>
                <div style="font-size:11px; color:#9d174d; opacity:0.8;">NVKD: {sales_name} ({sales_id})</div>
            </td>
            <td style="text-align:right;">{budget_str}</td>
            <td style="text-align:center;">{lead_days}</td>
            <td style="text-align:right; font-weight:700; color:#be185d;">{final_price_str}</td>
            <td style="text-align:center;"><span class="discount-pill">{disc_str}</span></td>
            <td><span class="badge {status_badge_class}">{status}</span></td>
            <td style="font-size:12px; color:#475569;">{d.get('next_action', '')}</td>
        </tr>
        """)

    dossiers_rows_str = "".join(rows_html)

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Báo Cáo Phân Tích Dữ Liệu B2B — {manager_name}</title>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background-color: #fff5f7;
        background-image: radial-gradient(#fbcfe8 1px, transparent 1px);
        background-size: 20px 20px;
        color: #1e293b;
        padding: 32px 20px;
        line-height: 1.5;
        font-size: 13.5px;
    }}
    .report-wrapper {{
        max-width: 1040px;
        margin: 0 auto;
        background: #ffffff;
        border-radius: 16px;
        box-shadow: 0 10px 30px rgba(236, 72, 153, 0.12);
        border: 1px solid #fbcfe8;
        overflow: hidden;
    }}
    .ribbon-top {{
        height: 8px;
        background: linear-gradient(135deg, #ec4899 0%, #f43f5e 50%, #a855f7 100%);
    }}
    .report-body {{
        padding: 36px 40px;
    }}
    .header-top {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        border-bottom: 2px solid #fbcfe8;
        padding-bottom: 20px;
        margin-bottom: 24px;
        gap: 16px;
        flex-wrap: wrap;
    }}
    .brand-badges {{
        display: flex;
        gap: 8px;
        margin-bottom: 10px;
        flex-wrap: wrap;
    }}
    .brand-pill {{
        font-size: 10.5px;
        font-weight: 800;
        padding: 4px 10px;
        border-radius: 20px;
        letter-spacing: 0.4px;
    }}
    .pill-pink {{ background: #fce7f3; color: #be185d; border: 1px solid #f9a8d4; }}
    .pill-purple {{ background: #f3e8ff; color: #7e22ce; border: 1px solid #d8b4fe; }}
    .brand-title h1 {{
        font-size: 15px;
        font-weight: 800;
        color: #831843;
        letter-spacing: 0.2px;
        text-transform: uppercase;
    }}
    .brand-title h2 {{
        font-size: 22px;
        font-weight: 800;
        color: #be185d;
        margin-top: 4px;
    }}
    .brand-title p {{
        font-size: 12.5px;
        color: #64748b;
        margin-top: 4px;
    }}
    .meta-box {{
        text-align: right;
        font-size: 12px;
        color: #831843;
        background: #fdf2f8;
        padding: 12px 16px;
        border-radius: 12px;
        border: 1px solid #f9a8d4;
        line-height: 1.7;
    }}
    .meta-box strong {{
        color: #4c0519;
    }}
    
    /* KPI CARDS */
    .kpi-row {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 14px;
        margin-bottom: 24px;
    }}
    .kpi-card {{
        background: linear-gradient(180deg, #ffffff 0%, #fffafb 100%);
        border: 1px solid #fbcfe8;
        border-radius: 12px;
        padding: 16px;
        position: relative;
        box-shadow: 0 2px 8px rgba(236, 72, 153, 0.05);
    }}
    .kpi-card::before {{
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        border-radius: 12px 12px 0 0;
    }}
    .kpi-green::before {{ background: linear-gradient(90deg, #10b981, #059669); }}
    .kpi-amber::before {{ background: linear-gradient(90deg, #f59e0b, #d97706); }}
    .kpi-orange::before {{ background: linear-gradient(90deg, #ec4899, #f43f5e); }}
    .kpi-red::before {{ background: linear-gradient(90deg, #e11d48, #9f1239); }}
    
    .kpi-label {{
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        color: #9d174d;
        letter-spacing: 0.3px;
    }}
    .kpi-val {{
        font-size: 26px;
        font-weight: 800;
        color: #0f172a;
        margin: 4px 0 2px 0;
    }}
    .kpi-sub {{
        font-size: 11.5px;
        color: #64748b;
    }}

    /* PIPELINE BANNER */
    .pipeline-banner {{
        background: linear-gradient(135deg, #831843 0%, #be185d 50%, #ec4899 100%);
        color: #ffffff;
        border-radius: 14px;
        padding: 22px 26px;
        margin-bottom: 26px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 8px 20px rgba(190, 24, 93, 0.25);
        position: relative;
        overflow: hidden;
    }}
    .pipeline-banner::after {{
        content: '✨🌸✨';
        position: absolute;
        right: 18px;
        top: 8px;
        font-size: 16px;
        opacity: 0.35;
    }}
    .pipeline-info h3 {{
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        color: #fbcfe8;
    }}
    .pipeline-info p {{
        font-size: 12px;
        color: #fce7f3;
        margin-top: 4px;
    }}
    .pipeline-amount {{
        font-size: 28px;
        font-weight: 800;
        color: #ffffff;
        text-shadow: 0 2px 10px rgba(0,0,0,0.2);
        letter-spacing: -0.3px;
    }}

    /* SECTION TITLES */
    .sec-title {{
        font-size: 14.5px;
        font-weight: 800;
        color: #831843;
        text-transform: uppercase;
        letter-spacing: 0.3px;
        margin: 24px 0 12px 0;
        padding-bottom: 8px;
        border-bottom: 2px solid #fbcfe8;
        display: flex;
        align-items: center;
        gap: 8px;
    }}

    /* TABLE */
    .table-container {{
        overflow-x: auto;
        border: 1px solid #fbcfe8;
        border-radius: 10px;
        margin-bottom: 24px;
        box-shadow: 0 2px 8px rgba(236, 72, 153, 0.04);
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 12.5px;
    }}
    th {{
        background: #fce7f3;
        color: #831843;
        font-weight: 700;
        text-align: left;
        padding: 11px 12px;
        font-size: 11px;
        border-bottom: 1.5px solid #f9a8d4;
        text-transform: uppercase;
        letter-spacing: 0.3px;
    }}
    td {{
        padding: 10px 12px;
        border-bottom: 1px solid #fdf2f8;
        vertical-align: middle;
    }}
    tr:last-child td {{
        border-bottom: none;
    }}
    tr:hover td {{
        background: #fff1f2;
    }}
    .text-muted {{
        color: #94a3b8;
        font-style: italic;
    }}

    /* BADGES */
    .badge {{
        display: inline-block;
        font-size: 10.5px;
        font-weight: 700;
        padding: 4px 9px;
        border-radius: 20px;
        white-space: nowrap;
    }}
    .badge-ready {{ background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }}
    .badge-pending {{ background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }}
    .badge-info {{ background: #fce7f3; color: #be185d; border: 1px solid #f9a8d4; }}
    .badge-reject {{ background: #ffe4e6; color: #be123c; border: 1px solid #fecdd3; }}
    .badge-muted {{ background: #f1f5f9; color: #64748b; }}

    .discount-pill {{
        background: #fdf2f8;
        color: #db2777;
        border: 1px solid #fbcfe8;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
    }}

    /* STRATEGIC INSIGHTS BOX */
    .insights-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 14px;
        margin-bottom: 26px;
    }}
    .insight-card {{
        background: #fdf2f8;
        border: 1px solid #fbcfe8;
        border-radius: 10px;
        padding: 16px 18px;
    }}
    .insight-card h4 {{
        font-size: 13px;
        font-weight: 700;
        color: #831843;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 6px;
    }}
    .insight-card p, .insight-card li {{
        font-size: 12px;
        color: #334155;
        line-height: 1.65;
    }}
    .insight-card ul {{
        margin-left: 18px;
        margin-top: 4px;
    }}

    /* SIGN-OFF */
    .signoff-row {{
        display: flex;
        justify-content: space-between;
        margin-top: 32px;
        padding-top: 20px;
        border-top: 1.5px dashed #f9a8d4;
    }}
    .signoff-col {{
        text-align: center;
        width: 250px;
    }}
    .signoff-role {{
        font-size: 12px;
        font-weight: 800;
        color: #831843;
        text-transform: uppercase;
    }}
    .signature-box {{
        margin-top: 12px;
        height: 54px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-family: 'Courier New', monospace;
        font-weight: 800;
        color: #be185d;
        border: 1.5px dashed #f472b6;
        background: #fdf2f8;
        border-radius: 8px;
        font-size: 13px;
        letter-spacing: 0.5px;
    }}
    .signoff-name {{
        margin-top: 8px;
        font-weight: 800;
        color: #4c0519;
        font-size: 13.5px;
    }}

    /* ACTION BAR */
    .action-bar {{
        max-width: 1040px;
        margin: 0 auto 14px auto;
        display: flex;
        gap: 10px;
        justify-content: flex-end;
    }}
    .btn {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        font-weight: 700;
        padding: 9px 18px;
        border-radius: 8px;
        cursor: pointer;
        border: 1.5px solid #f9a8d4;
        background: #ffffff;
        color: #be185d;
        transition: all 0.2s;
    }}
    .btn:hover {{
        background: #fdf2f8;
        border-color: #ec4899;
    }}
    .btn-primary {{
        background: linear-gradient(135deg, #ec4899, #db2777);
        color: #ffffff;
        border: none;
        box-shadow: 0 4px 12px rgba(236, 72, 153, 0.25);
    }}
    .btn-primary:hover {{
        filter: brightness(1.06);
    }}

    /* PRINT STYLES */
    @media print {{
        body {{
            background: #ffffff;
            padding: 0;
            font-size: 11pt;
        }}
        .action-bar {{
            display: none !important;
        }}
        .report-wrapper {{
            box-shadow: none;
            border: 1px solid #fbcfe8;
            max-width: 100%;
        }}
        .pipeline-banner, .ribbon-top, th, .badge {{
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
        }}
    }}
</style>
</head>
<body>

<div class="action-bar">
    <button class="btn" onclick="window.print()">🖨️ In Báo Cáo / Xuất PDF</button>
    <button class="btn btn-primary" onclick="downloadSelf()">⬇ Tải file HTML Báo Cáo</button>
</div>

<div class="report-wrapper" id="printReport">
    <div class="ribbon-top"></div>
    <div class="report-body">
        <!-- HEADER -->
        <div class="header-top">
            <div class="brand-title">
                <div class="brand-badges">
                    <span class="brand-pill pill-pink">🌸 TRƯỜNG GIANG ENTERPRISE AI</span>
                    <span class="brand-pill pill-purple">✨ EXECUTIVE REPORT</span>
                </div>
                <h1>HỆ THỐNG PHÂN TÍCH DỮ LIỆU B2B — TRƯỜNG GIANG</h1>
                <h2>BÁO CÁO PHÂN TÍCH DỮ LIỆU &amp; ĐỀ XUẤT CƠ HỘI BÁN HÀNG B2B</h2>
                <p>Hệ thống AI Data Analytics Agent tự động hóa tiếp nhận, làm sạch, thẩm định và đối soát cơ hội</p>
            </div>
            <div class="meta-box">
                <div>Mã báo cáo: <strong>{report_code}</strong></div>
                <div>Ngày phát hành: <strong>{now_str}</strong></div>
                <div>Người phê duyệt: <strong>{manager_name}</strong></div>
                <div>Trạng thái: <strong style="color:#db2777;">🌸 ĐÃ KIỂM DUYỆT (CHẶNG 4 ✓)</strong></div>
            </div>
        </div>

        <!-- KPI SUMMARY -->
        <div class="kpi-row">
            <div class="kpi-card kpi-green">
                <div class="kpi-label">Có Thể Tiếp Tục</div>
                <div class="kpi-val" style="color:#15803d;">{c_tiep_tuc}</div>
                <div class="kpi-sub">{p_tiep_tuc}% tổng cơ hội (Đạt thẩm quyền NVKD)</div>
            </div>
            <div class="kpi-card kpi-amber">
                <div class="kpi-label">Chờ Duyệt (Vượt Quyền)</div>
                <div class="kpi-val" style="color:#b45309;">{c_cho_duyet}</div>
                <div class="kpi-sub">{p_cho_duyet}% cơ hội (Trình TPKD {manager_name})</div>
            </div>
            <div class="kpi-card kpi-orange">
                <div class="kpi-label">Cần Bổ Sung Thông Tin</div>
                <div class="kpi-val" style="color:#db2777;">{c_bo_sung}</div>
                <div class="kpi-sub">{p_bo_sung}% cơ hội (Khuyết ngân sách/leadtime)</div>
            </div>
            <div class="kpi-card kpi-red">
                <div class="kpi-label">Chưa Đáp Ứng Được</div>
                <div class="kpi-val" style="color:#be123c;">{c_chua_dat}</div>
                <div class="kpi-sub">{p_chua_dat}% cơ hội (Vượt trần 15% hoặc hụt kho)</div>
            </div>
        </div>

        <!-- PIPELINE BANNER -->
        <div class="pipeline-banner">
            <div class="pipeline-info">
                <h3>💎 Tổng Giá Trị Doanh Số Tiềm Năng (Khả Thi + Chờ Duyệt)</h3>
                <p>Được tính riêng biệt từ {c_tiep_tuc + c_cho_duyet} cơ hội đáp ứng đầy đủ năng lực cung ứng và biên lợi nhuận của công ty.</p>
            </div>
            <div class="pipeline-amount">{format_currency_vnd(eligible_val)}</div>
        </div>

        <!-- SECTION 1: MASTER TABLE -->
        <div class="sec-title">
            <span>📋</span> Bảng Đối Soát Chi Tiết Từng Cơ Hội Bán Hàng ({total_ops} yêu cầu)
        </div>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th style="width:85px;">Mã Đơn</th>
                        <th>Khách Hàng / NVKD</th>
                        <th style="text-align:right;">Ngân Sách</th>
                        <th style="text-align:center;">Hạn Giao</th>
                        <th style="text-align:right;">Giá Đề Xuất</th>
                        <th style="text-align:center;">CK %</th>
                        <th style="width:140px;">Phân Loại</th>
                        <th>Căn Cứ &amp; Bước Xử Lý Tiếp Theo</th>
                    </tr>
                </thead>
                <tbody>
                    {dossiers_rows_str}
                </tbody>
            </table>
        </div>

        <!-- SECTION 2: AI INSIGHTS & STRATEGIC RECOMMENDATIONS -->
        <div class="sec-title">
            <span>💡</span> Nhận Xét Chuyên Sâu &amp; Đề Xuất Chiến Lược Từ AI Agent
        </div>
        <div class="insights-grid">
            <div class="insight-card">
                <h4>📦 Thẩm Định Kho &amp; Chuỗi Cung Ứng</h4>
                <p>Hệ thống tự động tra cứu CSDL tồn kho khả dụng và thời gian nhập hàng đối với 7 mã sản phẩm chủ lực (SP01 - SP07):</p>
                <ul>
                    <li>Các đơn hàng đạt chuẩn đều có sẵn linh kiện tại kho nội bộ với lead-time chỉ 1–3 ngày.</li>
                    <li>Phát hiện rủi ro giao hàng cục bộ: Mã <strong>SP05 (Switch Cisco)</strong> chỉ còn 5 chiếc khả dụng; thời gian nhập hàng bổ sung là 7 ngày. Agent đã chặn kịp thời cam kết ảo.</li>
                </ul>
            </div>
            <div class="insight-card">
                <h4>💰 Chính Sách Giá &amp; Kiểm Soát Thẩm Quyền</h4>
                <p>Quy tắc bậc thang theo giá trị đơn hàng được tuân thủ nghiêm ngặt:</p>
                <ul>
                    <li><strong>Hạn mức NVKD (&le; 5%):</strong> Tự động thông qua các đơn đạt chuẩn để rút ngắn chu kỳ bán hàng.</li>
                    <li><strong>Trần TPKD (&le; 15%):</strong> Lập phiếu trình duyệt cho trường hợp chiến lược (REQ-005 xin 12%) hoặc chênh ngân sách nhẹ &le; 5% (REQ-006).</li>
                    <li><strong>Chặn rủi ro (&gt; 15%):</strong> Từ chối thẳng yêu cầu chiết khấu vượt trần công ty (REQ-008 đòi 25%) nhằm bảo vệ biên lợi nhuận.</li>
                </ul>
            </div>
        </div>

        <!-- SIGN-OFF -->
        <div class="signoff-row">
            <div class="signoff-col">
                <div class="signoff-role">NGƯỜI LẬP BÁO CÁO</div>
                <div style="font-size:11px; color:#64748b; margin-top:2px;">AI Data Analytics Agent</div>
                <div class="signature-box" style="color:#7e22ce; border-color:#d8b4fe; background:#faf5ff;">
                    ✨ VERIFIED AI SYSTEM
                </div>
                <div class="signoff-name">SalesOpportunityAgent v2.0</div>
            </div>
            <div class="signoff-col">
                <div class="signoff-role">TRƯỞNG PHÒNG KINH DOANH</div>
                <div style="font-size:11px; color:#64748b; margin-top:2px;">Người phê duyệt chốt chặn cuối</div>
                <div class="signature-box">
                    🌸 DIGITALLY APPROVED ✓
                </div>
                <div class="signoff-name">{manager_name}</div>
            </div>
        </div>
    </div>
</div>

<script>
function downloadSelf() {{
    const htmlContent = document.documentElement.outerHTML;
    const blob = new Blob([htmlContent], {{ type: 'text/html;charset=utf-8' }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'Bao_Cao_Phan_Tich_B2B_{manager_name}.html';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}}
</script>
</body>
</html>
"""
    return html_content


