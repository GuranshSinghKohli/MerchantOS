import { Suspense } from "react";
import { AnalyticsPageView } from "@/components/section-view";
import { LoadingBoard } from "@/components/states";

export default function AnalyticsPage() {
  return (
    <Suspense fallback={<LoadingBoard />}>
      <AnalyticsPageView />
    </Suspense>
  );
}
