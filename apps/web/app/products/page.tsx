import { Suspense } from "react";
import { ProductsView } from "@/components/products-view";
import { LoadingBoard } from "@/components/states";

export default function ProductsPage() {
  return (
    <Suspense fallback={<LoadingBoard />}>
      <ProductsView />
    </Suspense>
  );
}
