from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.product_catalog import ProductRequestSource, ProductRequestStatus
from app.models.product_catalog import ProductReorderStatus, ProductTransferStatus
from app.models.product_catalog import StockMovementSourceType, StockMovementType


class AdminCatalogCategoryOut(BaseModel):
    id: UUID
    name: str
    code: str | None
    description: str | None
    display_order: int
    can_be_requested_by_professor: bool
    active: bool
    created_at: datetime
    updated_at: datetime


class AdminCatalogCategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    display_order: int = Field(default=0, ge=0, le=100000)
    can_be_requested_by_professor: bool = True
    active: bool = True


class AdminCatalogCategoryUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    display_order: int = Field(default=0, ge=0, le=100000)
    can_be_requested_by_professor: bool = True
    active: bool = True


class AdminCatalogProductOut(BaseModel):
    id: UUID
    category_id: UUID | None
    category_name: str | None
    primary_location_id: UUID | None
    primary_location_name: str | None
    title: str
    barcode: str | None
    price_excl_vat: Decimal
    price_incl_vat: Decimal
    vat_rate: Decimal
    stock_global_quantity: int
    reserve_stock: int
    reorder_status: ProductReorderStatus
    reorder_status_updated_at: datetime
    image_url: str | None
    short_description: str | None
    long_description: str | None
    web_link: str | None
    is_virtual: bool
    purchasable_online: bool
    is_public: bool
    active: bool
    created_at: datetime
    updated_at: datetime


class AdminCatalogProductCreateRequest(BaseModel):
    category_id: UUID | None = None
    primary_location_id: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    barcode: str | None = Field(default=None, max_length=120)
    price_excl_vat: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    price_incl_vat: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    vat_rate: Decimal = Field(default=Decimal("20.000"), ge=Decimal("0"), le=Decimal("100"))
    reserve_stock: int = Field(default=0, ge=0, le=1000000)
    reorder_status: ProductReorderStatus = ProductReorderStatus.NORMAL
    image_url: str | None = Field(default=None, max_length=4000)
    short_description: str | None = Field(default=None, max_length=500)
    long_description: str | None = Field(default=None, max_length=12000)
    web_link: str | None = Field(default=None, max_length=4000)
    is_virtual: bool = False
    purchasable_online: bool = False
    is_public: bool = True
    active: bool = True


class AdminCatalogProductUpdateRequest(AdminCatalogProductCreateRequest):
    pass


class AdminCatalogProductImageUploadOut(BaseModel):
    image_url: str
    storage_key: str


class AdminCatalogKitItemIn(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=1000)
    display_order: int = Field(default=0, ge=0, le=10000)


class AdminCatalogKitItemOut(BaseModel):
    product_id: UUID
    product_title: str
    quantity: int
    display_order: int
    unit_price_incl_vat: Decimal
    line_total_incl_vat: Decimal


class AdminCatalogKitOut(BaseModel):
    id: UUID
    category_id: UUID | None
    category_name: str | None
    code: str | None
    title: str
    image_url: str | None
    short_description: str | None
    long_description: str | None
    price_mode: Literal["calculated", "forced"] | str
    forced_price: Decimal | None
    currency: str
    price_effective_incl_vat: Decimal
    price_incl_vat: Decimal
    vat_rate: Decimal
    computed_price_incl_vat: Decimal
    use_in_manual_billing: bool
    use_in_enrollments: bool
    purchasable_online: bool
    is_public: bool
    active: bool
    items: list[AdminCatalogKitItemOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AdminCatalogKitCreateRequest(BaseModel):
    category_id: UUID | None = None
    code: str | None = Field(default=None, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    image_url: str | None = Field(default=None, max_length=4000)
    short_description: str | None = Field(default=None, max_length=500)
    long_description: str | None = Field(default=None, max_length=12000)
    price_mode: Literal["calculated", "forced"] = "calculated"
    forced_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    price_incl_vat: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    vat_rate: Decimal = Field(default=Decimal("20.000"), ge=Decimal("0"), le=Decimal("100"))
    use_in_manual_billing: bool = True
    use_in_enrollments: bool = True
    purchasable_online: bool = False
    is_public: bool = True
    active: bool = True
    items: list[AdminCatalogKitItemIn] = Field(default_factory=list)


class AdminCatalogKitUpdateRequest(AdminCatalogKitCreateRequest):
    pass


class AdminCatalogStockOut(BaseModel):
    product_id: UUID
    product_title: str
    location_id: UUID
    location_name: str
    inventory_quantity: int
    inventory_date: date | None
    real_quantity: int
    estimated_quantity: int
    inventory_updated_at: datetime
    real_updated_at: datetime
    estimated_updated_at: datetime
    updated_at: datetime


class AdminCatalogReorderProductOut(BaseModel):
    product_id: UUID
    title: str
    category_name: str | None
    stock_global_quantity: int
    reserve_stock: int
    reorder_status: ProductReorderStatus
    reorder_status_updated_at: datetime
    primary_location_id: UUID | None
    primary_location_name: str | None


class AdminCatalogReorderStatusUpdateRequest(BaseModel):
    reorder_status: ProductReorderStatus


class AdminCatalogStockTransferOut(BaseModel):
    id: UUID
    product_id: UUID
    product_title: str
    source_location_id: UUID
    source_location_name: str
    target_location_id: UUID
    target_location_name: str
    quantity: int
    planned_transfer_date: date | None
    assigned_to_user_id: UUID | None
    assigned_to_name: str | None
    requested_by_user_id: UUID | None
    requested_by_name: str | None
    status: ProductTransferStatus
    completed_by_user_id: UUID | None
    completed_by_name: str | None
    completed_at: datetime | None
    completed_transfer_date: date | None
    note: str | None
    created_at: datetime
    updated_at: datetime


class AdminCatalogStockTransferCreateRequest(BaseModel):
    product_id: UUID
    source_location_id: UUID
    target_location_id: UUID
    quantity: int = Field(default=1, ge=1, le=1000000)
    planned_transfer_date: date | None = None
    assigned_to_user_id: UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


class AdminCatalogStockTransferCompleteRequest(BaseModel):
    completed_transfer_date: date | None = None
    note: str | None = Field(default=None, max_length=2000)


class AdminCatalogStockTransferCancelRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class AdminCatalogStockInventoryUpdateRequest(BaseModel):
    inventory_quantity: int = Field(ge=0, le=1000000)
    inventory_date: date | None = None


class AdminStockEntryCreateRequest(BaseModel):
    product_id: UUID
    location_id: UUID
    quantity: Decimal = Field(gt=Decimal("0"), le=Decimal("1000000"), multiple_of=Decimal("1"))
    occurred_at: datetime | None = None
    source_type: StockMovementSourceType = StockMovementSourceType.OTHER
    source_reference: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=2000)
    attachment_key: str | None = Field(default=None, max_length=4000)


class AdminStockAdjustmentCreateRequest(BaseModel):
    product_id: UUID
    location_id: UUID
    quantity: Decimal = Field(le=Decimal("1000000"), multiple_of=Decimal("1"))
    occurred_at: datetime | None = None
    source_type: StockMovementSourceType = StockMovementSourceType.CORRECTION
    source_reference: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=2000)
    attachment_key: str | None = Field(default=None, max_length=4000)


class AdminStockMovementOut(BaseModel):
    id: UUID
    product_id: UUID
    product_title: str
    location_id: UUID
    location_name: str
    movement_type: StockMovementType
    quantity: Decimal
    occurred_at: datetime
    source_type: StockMovementSourceType
    source_reference: str | None
    note: str | None
    attachment_key: str | None
    created_by: UUID | None
    created_by_name: str | None
    meta: dict | None
    created_at: datetime
    updated_at: datetime


class AdminStockSnapshotOut(BaseModel):
    product_id: UUID
    product_title: str
    stock_global: int
    stock_location: int
    stock_reserved: int


class AdminStockEntryCreateResponse(BaseModel):
    movement_id: UUID
    stock_snapshot: AdminStockSnapshotOut


class AdminStockMovementListOut(BaseModel):
    items: list[AdminStockMovementOut]
    total: int
    page: int
    page_size: int


class AdminCatalogProductStockOut(BaseModel):
    product_id: UUID
    product_title: str
    stock_global: int
    stock_reserved: int
    stock_by_location: list[AdminCatalogStockOut]
    recent_movements: list[AdminStockMovementOut]


class AdminCatalogRequestOut(BaseModel):
    id: UUID
    student_user_id: UUID
    student_name: str
    product_id: UUID
    product_title: str
    location_id: UUID
    location_name: str
    quantity: int
    requested_by_user_id: UUID | None
    requested_by_name: str | None
    request_source: ProductRequestSource
    status: ProductRequestStatus
    requested_at: datetime
    admin_reviewed_by_user_id: UUID | None
    admin_reviewed_by_name: str | None
    admin_reviewed_at: datetime | None
    accepted: bool | None
    should_bill: bool | None
    manual_transaction_id: UUID | None
    delivered_by_user_id: UUID | None
    delivered_by_name: str | None
    delivery_marked_by_user_id: UUID | None
    delivery_marked_by_name: str | None
    delivery_marked_at: datetime | None
    note: str | None
    stock_real_quantity: int | None
    stock_estimated_quantity: int | None


class AdminCatalogRequestCreateRequest(BaseModel):
    student_user_id: UUID
    product_id: UUID
    location_id: UUID
    quantity: int = Field(default=1, ge=1, le=1000)
    should_bill: bool = False
    note: str | None = Field(default=None, max_length=2000)


class AdminCatalogRequestReviewRequest(BaseModel):
    accept: bool
    should_bill: bool = False
    note: str | None = Field(default=None, max_length=2000)


class AdminCatalogRequestDeliverRequest(BaseModel):
    delivered_by_user_id: UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


class ProfessorCatalogStudentOut(BaseModel):
    user_id: UUID
    display_name: str


class ProfessorCatalogRequestCreateRequest(BaseModel):
    student_user_id: UUID
    product_id: UUID
    location_id: UUID
    quantity: int = Field(default=1, ge=1, le=1000)
    note: str | None = Field(default=None, max_length=2000)


class ProfessorCatalogRequestDeliverRequest(BaseModel):
    delivered_by_user_id: UUID | None = None
    note: str | None = Field(default=None, max_length=2000)
