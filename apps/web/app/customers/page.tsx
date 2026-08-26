import { Suspense } from "react";
import { CustomersView } from "@/components/section-view";
import { LoadingBoard } from "@/components/states";

export default function CustomersPage() {
  return (
    <Suspense fallback={<LoadingBoard />}>
      <CustomersView />
    </Suspense>
  );
}
