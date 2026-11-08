/**
 * Test-only ambient declarations.
 *
 * The frontend deliberately has no `@types/node` dependency, but a few unit tests
 * read committed source/build files (tokens.css, styles.css, dist/index.html) from
 * disk to verify colour contrast and Local Mode constraints. Only the helpers those
 * tests use are declared here.
 */
declare module "node:fs" {
  export function existsSync(path: string | URL): boolean;
  export function readFileSync(path: string | URL, options: { encoding: "utf8" }): string;
}

/** Vitest runs with the `frontend/` package as the working directory. */
declare const process: { cwd(): string };
