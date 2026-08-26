import { Suspense } from "react";
import { InventoryView } from "@/components/section-view";
import { LoadingBoard } from "@/components/states";

export default function InventoryPage() {
  return (
    <Suspense fallback={<LoadingBoard />}>
      <InventoryView />
    </Suspense>
  );
}
