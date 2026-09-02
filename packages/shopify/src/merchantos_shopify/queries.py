"""Official GraphQL Admin API 2026-07 read queries.

Field names taken from:
https://shopify.dev/docs/api/admin-graphql/2026-07/queries/products
https://shopify.dev/docs/api/admin-graphql/2026-07/queries/orders
https://shopify.dev/docs/api/admin-graphql/2026-07/queries/customers
https://shopify.dev/docs/api/admin-graphql/2026-07/queries/locations
https://shopify.dev/docs/api/admin-graphql/2026-07/queries/productVariants
https://shopify.dev/docs/api/admin-graphql/2026-07/objects/InventoryLevel
"""

from merchantos_shopify.constants import ADMIN_API_VERSION

_ = ADMIN_API_VERSION

PRODUCT_FIELDS = """
  id
  title
  status
  vendor
  productType
  tags
  publishedAt
  variants(first: 100) {
    edges {
      node {
        id
        title
        sku
        price
        compareAtPrice
        inventoryItem {
          id
          unitCost { amount }
        }
      }
    }
  }
"""

ORDER_FIELDS = """
  id
  name
  processedAt
  cancelledAt
  displayFinancialStatus
  displayFulfillmentStatus
  currencyCode
  subtotalPriceSet { shopMoney { amount currencyCode } }
  totalDiscountsSet { shopMoney { amount } }
  totalPriceSet { shopMoney { amount currencyCode } }
  customer { id }
  lineItems(first: 100) {
    edges {
      node {
        id
        quantity
        originalUnitPriceSet { shopMoney { amount } }
        totalDiscountSet { shopMoney { amount } }
        variant { id }
      }
    }
  }
"""

CUSTOMER_FIELDS = """
  id
  defaultEmailAddress { emailAddress }
  numberOfOrders
  state
  amountSpent { amount }
"""

# New apps often lack protected-customer-data access for email. Id and spend still sync.
CUSTOMER_FIELDS_PUBLIC = """
  id
  numberOfOrders
  state
  amountSpent { amount }
"""

LOCATION_FIELDS = """
  id
  name
  isActive
"""

PRODUCTS_PAGE = f"""
query ProductsPage($first: Int!, $after: String, $query: String) {{
  products(first: $first, after: $after, query: $query) {{
    pageInfo {{ hasNextPage endCursor }}
    edges {{ node {{ {PRODUCT_FIELDS} }} }}
  }}
}}
"""

ORDERS_PAGE = f"""
query OrdersPage($first: Int!, $after: String, $query: String) {{
  orders(first: $first, after: $after, query: $query) {{
    pageInfo {{ hasNextPage endCursor }}
    edges {{ node {{ {ORDER_FIELDS} }} }}
  }}
}}
"""

CUSTOMERS_PAGE = f"""
query CustomersPage($first: Int!, $after: String, $query: String) {{
  customers(first: $first, after: $after, query: $query) {{
    pageInfo {{ hasNextPage endCursor }}
    edges {{ node {{ {CUSTOMER_FIELDS} }} }}
  }}
}}
"""

CUSTOMERS_PAGE_PUBLIC = f"""
query CustomersPagePublic($first: Int!, $after: String, $query: String) {{
  customers(first: $first, after: $after, query: $query) {{
    pageInfo {{ hasNextPage endCursor }}
    edges {{ node {{ {CUSTOMER_FIELDS_PUBLIC} }} }}
  }}
}}
"""

LOCATIONS_PAGE = f"""
query LocationsPage($first: Int!, $after: String) {{
  locations(first: $first, after: $after, includeInactive: true) {{
    pageInfo {{ hasNextPage endCursor }}
    edges {{ node {{ {LOCATION_FIELDS} }} }}
  }}
}}
"""

INVENTORY_PAGE = """
query InventoryPage($first: Int!, $after: String) {
  productVariants(first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        inventoryItem {
          id
          inventoryLevels(first: 20) {
            edges {
              node {
                location { id }
                quantities(names: ["available", "on_hand"]) {
                  name
                  quantity
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

PRODUCT_NODE = f"""
query ProductNode($id: ID!) {{
  product(id: $id) {{ {PRODUCT_FIELDS} }}
}}
"""

ORDER_NODE = f"""
query OrderNode($id: ID!) {{
  order(id: $id) {{ {ORDER_FIELDS} }}
}}
"""

CUSTOMER_NODE = f"""
query CustomerNode($id: ID!) {{
  customer(id: $id) {{ {CUSTOMER_FIELDS} }}
}}
"""

LOCATION_NODE = f"""
query LocationNode($id: ID!) {{
  location(id: $id) {{ {LOCATION_FIELDS} }}
}}
"""
