from typing import NewType
from uuid import UUID

MerchantId = NewType("MerchantId", UUID)
StoreId = NewType("StoreId", UUID)
UserId = NewType("UserId", UUID)
RequestId = NewType("RequestId", UUID)
