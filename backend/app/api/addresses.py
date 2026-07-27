"""
Address API Endpoints - Attack Address List
"""
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response as HTTPResponse
from pydantic import BaseModel
import csv
import io
from sqlalchemy.orm import Session
from sqlalchemy import or_
import urllib.request
import json

from app.models.base import get_db
from app.models.address import Address
from app.schemas.address import AddressCreate, AddressUpdate, AddressResponse
from app.schemas.common import Response, PaginatedResponse, PaginatedData
from app.api.security import get_current_user
from app.models.user import User


# ── Helpers ────────────────────────────────────────────────────────────────────

# ISO 代码 → 中文国家名映射
_COUNTRY_NAME_MAP = {
    "CN": "中国", "US": "美国", "DE": "德国", "JP": "日本", "GB": "英国",
    "FR": "法国", "RU": "俄罗斯", "KR": "韩国", "IN": "印度", "BR": "巴西",
    "CA": "加拿大", "AU": "澳大利亚", "IT": "意大利", "ES": "西班牙",
    "NL": "荷兰", "SG": "新加坡", "HK": "香港", "TW": "台湾", "SE": "瑞典",
    "NO": "挪威", "DK": "丹麦", "FI": "芬兰", "PL": "波兰", "CH": "瑞士",
    "AT": "奥地利", "BE": "比利时", "IE": "爱尔兰", "CZ": "捷克", "PT": "葡萄牙",
    "GR": "希腊", "TR": "土耳其", "UA": "乌克兰", "VN": "越南", "TH": "泰国",
    "MY": "马来西亚", "ID": "印度尼西亚", "PH": "菲律宾", "PK": "巴基斯坦",
    "BD": "孟加拉", "AE": "阿联酋", "SA": "沙特", "IL": "以色列", "EG": "埃及",
    "NG": "尼日利亚", "ZA": "南非", "MX": "墨西哥", "AR": "阿根廷", "CL": "智利",
    "CO": "哥伦比亚", "PE": "秘鲁", "VE": "委内瑞拉", "RO": "罗马尼亚", "HU": "匈牙利",
    "BG": "保加利亚", "HR": "克罗地亚", "RS": "塞尔维亚", "SK": "斯洛伐克", "LT": "立陶宛",
    "LV": "拉脱维亚", "EE": "爱沙尼亚", "KZ": "哈萨克斯坦", "UZ": "乌兹别克斯坦",
    "IR": "伊朗", "IQ": "伊拉克", "LY": "利比亚", "TN": "突尼斯", "DZ": "阿尔及利亚",
    "MA": "摩洛哥", "KE": "肯尼亚", "GH": "加纳", "TZ": "坦桑尼亚", "UG": "乌干达",
    "ET": "埃塞俄比亚", "AO": "安哥拉", "MZ": "莫桑比克", "ZW": "津巴布韦", "NP": "尼泊尔",
    "LK": "斯里兰卡", "MM": "缅甸", "KH": "柬埔寨", "LA": "老挝", "MN": "蒙古",
    "NP": "尼泊尔", "BT": "不丹", "BN": "文莱", "TL": "东帝汶", "FJ": "斐济",
    "PG": "巴布亚新几内亚", "NC": "新喀里多尼亚", "NZ": "新西兰", "GU": "关岛",
    "PR": "波多黎各", "PA": "巴拿马", "CR": "哥斯达黎加", "GT": "危地马拉", "HN": "洪都拉斯",
    "SV": "萨尔瓦多", "NI": "尼加拉瓜", "CU": "古巴", "JM": "牙买加", "TT": "特立尼达和多巴哥",
    "BS": "巴哈马", "BB": "巴巴多斯", "BH": "巴林", "KW": "科威特", "OM": "阿曼",
    "QA": "卡塔尔", "JO": "约旦", "LB": "黎巴嫩", "SY": "叙利亚", "YE": "也门",
    "AF": "阿富汗", "KG": "吉尔吉斯斯坦", "TJ": "塔吉克斯坦", "TM": "土库曼斯坦", "GE": "格鲁吉亚",
    "AM": "亚美尼亚", "AZ": "阿塞拜疆", "BY": "白俄罗斯", "MD": "摩尔多瓦", "AL": "阿尔巴尼亚",
    "MK": "北马其顿", "BA": "波黑", "ME": "黑山", "SI": "斯洛文尼亚", "IS": "冰岛",
    "LU": "卢森堡", "MT": "马耳他", "CY": "塞浦路斯", "AD": "安道尔", "MC": "摩纳哥",
    "SM": "圣马力诺", "VA": "梵蒂冈", "GI": "直布罗陀", "FO": "法罗群岛", "GL": "格陵兰",
    "RE": "留尼汪", "MQ": "马提尼克", "GP": "瓜德罗普", "GF": "法属圭亚那", "YT": "马约特",
    "PM": "圣皮埃尔和密克隆", "WF": "瓦利斯和富图纳", "PF": "法属波利尼西亚", "WS": "萨摩亚",
    "TO": "汤加", "VU": "瓦努阿图", "KI": "基里巴斯", "NR": "瑙鲁", "PW": "帕劳",
    "FM": "密克罗尼西亚", "MH": "马绍尔群岛", "MP": "北马里亚纳群岛", "VI": "美属维尔京群岛",
    "AS": "美属萨摩亚", "CK": "库克群岛", "NU": "纽埃", "TK": "托克劳",
    "IP": "未分配", "A1": "匿名代理", "A2": "卫星", "XX": "未知",
}


def _lookup_country_single(ip: str) -> str:
    """通过 ipinfo.io 查询单个 IP 的国家归属（返回中文国家名）。失败返回空。"""
    if not ip:
        return ""
    try:
        req = urllib.request.Request(
            f"https://ipinfo.io/{ip.strip()}/json",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode())
            code = data.get("country", "") or ""
            return _COUNTRY_NAME_MAP.get(code, code) if code else ""
    except Exception:
        return ""


# ── Request Models ────────────────────────────────────────────────────────────

class BatchDeleteRequest(BaseModel):
    ids: List[int]


class BatchCountryLookupRequest(BaseModel):
    """批量查询国家归属 — 传入地址 IDs 列表"""
    ids: List[int]


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/addresses", tags=["Addresses"])


@router.get("", response_model=PaginatedResponse[AddressResponse])
async def list_addresses(
    keyword: str = Query(default="", description="Search IP/domain/country"),
    status: str = Query(default="", description="Filter by status"),
    severity: str = Query(default="", description="Filter by severity"),
    date_from: str = Query(default="", description="Start date YYYY-MM-DD"),
    date_to: str = Query(default="", description="End date YYYY-MM-DD"),
    sort_field: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List addresses with filtering and pagination"""
    query = db.query(Address)

    if keyword:
        query = query.filter(
            or_(
                Address.ip_address.like(f"%{keyword}%"),
                Address.country.like(f"%{keyword}%"),
                Address.domain.like(f"%{keyword}%")
            )
        )
    if status:
        query = query.filter(Address.status == status)
    if severity:
        query = query.filter(Address.severity == severity)
    def _parse_dt(val):
        if not val:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue
        return None

    if date_from:
        dt = _parse_dt(date_from)
        if dt:
            query = query.filter(Address.created_at >= dt)

    if date_to:
        dt = _parse_dt(date_to)
        if dt:
            if len(date_to) <= 10:
                dt = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            query = query.filter(Address.created_at <= dt)

    allowed_sort = {"created_at", "ip_address", "attack_count", "duration", "severity", "start_time"}
    if sort_field not in allowed_sort:
        sort_field = "created_at"
    col = getattr(Address, sort_field)
    query = query.order_by(col.asc() if sort_order == "asc" else col.desc())

    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()

    return PaginatedResponse(
        data=PaginatedData(
            total=total,
            page=page,
            page_size=page_size,
            list=[AddressResponse.model_validate(a) for a in rows]
        )
    )


def _parse_dt_str(val):
    """Parse date/datetime string in common formats"""
    if not val:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


@router.get("/export")
async def export_addresses(
    keyword: str = Query(default="", description="Search IP/domain/country"),
    status: str = Query(default="", description="Filter by status"),
    severity: str = Query(default="", description="Filter by severity"),
    date_from: str = Query(default="", description="Start date YYYY-MM-DD"),
    date_to: str = Query(default="", description="End date YYYY-MM-DD"),
    sort_field: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """导出地址列表为 CSV（参数同列表查询，不分页）"""
    query = db.query(Address)

    if keyword:
        query = query.filter(
            or_(
                Address.ip_address.like(f"%{keyword}%"),
                Address.country.like(f"%{keyword}%"),
                Address.domain.like(f"%{keyword}%")
            )
        )
    if status:
        query = query.filter(Address.status == status)
    if severity:
        query = query.filter(Address.severity == severity)

    if date_from:
        dt = _parse_dt_str(date_from)
        if dt:
            query = query.filter(Address.created_at >= dt)
    if date_to:
        dt = _parse_dt_str(date_to)
        if dt:
            if len(date_to) <= 10:
                dt = dt.replace(hour=23, minute=59, second=59)
            query = query.filter(Address.created_at <= dt)

    allowed_sort = {"created_at", "ip_address", "attack_count", "duration", "severity", "start_time"}
    if sort_field not in allowed_sort:
        sort_field = "created_at"
    col = getattr(Address, sort_field)
    query = query.order_by(col.asc() if sort_order == "asc" else col.desc())

    rows = query.all()

    def _fmt_dt(v):
        return v.strftime("%Y-%m-%d %H:%M:%S") if v else ""

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "IP地址", "所属国家", "域名", "严重程度", "攻击次数",
        "持续时间(秒)", "状态", "开始时间", "结束时间", "来源", "备注"
    ])
    for a in rows:
        writer.writerow([
            a.ip_address or "",
            a.country or "",
            a.domain or "",
            a.severity or "",
            a.attack_count or 0,
            a.duration or 0,
            a.status or "",
            _fmt_dt(a.start_time),
            _fmt_dt(a.end_time),
            a.source or "",
            (a.remark or "").replace("\r\n", " ").replace("\n", " ")
        ])

    # 加 UTF-8 BOM，确保 Excel 正确识别中文
    csv_bytes = ("\ufeff" + buf.getvalue()).encode("utf-8")
    filename = f"addresses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return HTTPResponse(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.post("", response_model=Response[AddressResponse])
async def create_address(
    request: AddressCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new address — 入库时若 country 为空则自动通过 ipinfo.io 查询 IP 国家归属"""
    country = request.country
    if not country and request.ip_address:
        country = _lookup_country_single(request.ip_address)

    addr = Address(
        ip_address=request.ip_address,
        country=country,
        domain=request.domain,
        start_time=request.start_time,
        end_time=request.end_time,
        duration=request.duration,
        attack_count=request.attack_count,
        severity=request.severity,
        status=request.status,
        source=request.source,
        remark=request.remark
    )
    db.add(addr)
    db.commit()
    db.refresh(addr)
    return Response(msg="添加成功", data=AddressResponse.model_validate(addr))


@router.get("/{addr_id}", response_model=Response[AddressResponse])
async def get_address(
    addr_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    addr = db.query(Address).filter(Address.id == addr_id).first()
    if not addr:
        return Response(code=404, msg="地址不存在")
    return Response(data=AddressResponse.model_validate(addr))


@router.put("/{addr_id}", response_model=Response[AddressResponse])
async def update_address(
    addr_id: int,
    request: AddressUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    addr = db.query(Address).filter(Address.id == addr_id).first()
    if not addr:
        return Response(code=404, msg="地址不存在")
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(addr, field, value)
    db.commit()
    db.refresh(addr)
    return Response(msg="更新成功", data=AddressResponse.model_validate(addr))


@router.delete("/{addr_id}", response_model=Response)
async def delete_address(
    addr_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    addr = db.query(Address).filter(Address.id == addr_id).first()
    if not addr:
        return Response(code=404, msg="地址不存在")
    db.delete(addr)
    db.commit()
    return Response(msg="删除成功")


@router.post("/batch-delete", response_model=Response)
async def batch_delete(
    request: BatchDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ids = request.ids
    if not ids:
        return Response(code=400, msg="请选择要删除的记录")
    db.query(Address).filter(Address.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return Response(msg=f"已删除 {len(ids)} 条记录")


@router.post("/batch-lookup-country", response_model=Response)
async def batch_lookup_country(
    request: BatchCountryLookupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """批量查询地址国家归属，查到后写入 MySQL（只更新 country 为空的记录）"""
    ids = request.ids
    if not ids:
        return Response(code=400, msg="请选择要查询的记录")
    addresses = db.query(Address).filter(Address.id.in_(ids)).all()
    if not addresses:
        return Response(code=404, msg="未找到对应的地址记录")
    updated = 0
    for addr in addresses:
        if not addr.country:
            country = _lookup_country_single(addr.ip_address)
            if country:
                addr.country = country
                updated += 1
    db.commit()
    return Response(
        msg=f"查询完成，共更新 {updated} 条记录的国家归属（已有国家信息的未做修改）",
        data={"updated": updated, "total": len(addresses)}
    )


@router.post("/migrate-countries", response_model=Response)
async def migrate_countries(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """一次性迁移：将所有历史 ISO 国家码（如 US/DE/CN）翻译为中文名。"""
    all_addresses = db.query(Address).filter(Address.country != None, Address.country != "").all()
    migrated = 0
    for addr in all_addresses:
        # 如果当前值不是已知的中文名，尝试翻译
        code = addr.country.strip()
        if code and code not in _COUNTRY_NAME_MAP.values() and code in _COUNTRY_NAME_MAP:
            addr.country = _COUNTRY_NAME_MAP[code]
            migrated += 1
    db.commit()
    return Response(msg=f"迁移完成，共翻译 {migrated} 条国家记录", data={"migrated": migrated})
