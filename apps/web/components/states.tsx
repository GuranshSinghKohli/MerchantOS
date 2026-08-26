import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function LoadingBoard() {
  return (
    <div aria-busy="true" aria-live="polite" className="grid gap-4">
      <span className="sr-only">Loading analytics</span>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-24" />
        ))}
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}

export function EmptyBoard({ title, body }: { title: string; body: string }) {
  return (
    <Card>
      <CardContent className="py-10 text-center">
        <p className="text-sm font-medium">{title}</p>
        <p className="mt-2 text-sm text-[hsl(var(--muted-foreground))]">{body}</p>
      </CardContent>
    </Card>
  );
}

export function ErrorBoard({ message }: { message: string }) {
  return (
    <Card className="border-[hsl(var(--danger))]/40">
      <CardContent className="py-8">
        <p className="text-sm font-medium">We could not load this view</p>
        <p className="mt-2 text-sm text-[hsl(var(--muted-foreground))]">{message}</p>
      </CardContent>
    </Card>
  );
}
