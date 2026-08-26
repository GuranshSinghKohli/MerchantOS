import { Suspense } from "react";
import { InsightsView } from "@/components/section-view";
import { LoadingBoard } from "@/components/states";

export default function InsightsPage() {
  return (
    <Suspense fallback={<LoadingBoard />}>
      <InsightsView />
    </Suspense>
  );
}
