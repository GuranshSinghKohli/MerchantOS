from enum import StrEnum


class ToolPermission(StrEnum):
    ANALYTICS_READ = "analytics:read"
    PRODUCTS_READ = "products:read"
    INVENTORY_READ = "inventory:read"
    ORDERS_READ = "orders:read"
    CUSTOMERS_READ = "customers:read"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
