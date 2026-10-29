// Shown the moment a nav link is pressed, while the page renders on the server (every page reads Neon fresh), and
// prefetched with the link, so navigation never looks stuck.
const block = "rounded-lg border border-line bg-surface";

export default function Loading() {
  return (
    <div role="status" aria-label="Loading" className="flex flex-col gap-6 motion-safe:animate-pulse">
      <div className="flex flex-col gap-2">
        <div className="h-8 w-40 rounded-md bg-raised" />
        <div className="h-4 w-72 max-w-full rounded-md bg-raised/70" />
      </div>
      <div className="grid grid-cols-2 gap-3 md:gap-4 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <div key={i} className={`${block} h-28`} />)}
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className={`${block} h-80`} />
        <div className={`${block} hidden h-80 lg:block`} />
      </div>
    </div>
  );
}
