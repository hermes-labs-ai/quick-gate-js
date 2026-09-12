// Same shape as the clean fixture, with one real type error: greeting() returns
// number, not string.
export function greeting(name: string): string {
  return 42;
}
