import { Suspense } from "react";
import { OverviewView } from "@/components/overview-view";
import { LoadingBoard } from "@/components/states";

export const dynamic = "force-dynamic";

export default function OverviewPage() {
  return (
    <Suspense fallback={<LoadingBoard />}>
      <OverviewView />
    </Suspense>
  );
}
