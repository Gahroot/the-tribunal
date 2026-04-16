import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-4 text-center p-8">
        <h2 className="text-4xl font-bold text-foreground">404</h2>
        <p className="text-lg text-muted-foreground">
          The page you are looking for does not exist.
        </p>
        <Link
          href="/dashboard"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
