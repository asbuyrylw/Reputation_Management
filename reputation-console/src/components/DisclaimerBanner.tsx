export function DisclaimerBanner({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
      {children}
    </div>
  );
}
