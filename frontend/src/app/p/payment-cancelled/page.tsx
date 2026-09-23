export default function PaymentCancelledPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-4 px-6 py-12 text-center">
      <h1 className="text-2xl font-semibold">Checkout not completed</h1>
      <p className="text-muted-foreground">
        No payment or card setup was completed. If this was for an appointment, your booking is still confirmed.
      </p>
    </main>
  );
}
