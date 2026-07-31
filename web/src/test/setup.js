import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Explicit because testing-library only auto-registers this when vitest runs with
// `globals: true`. Without it every render piles up in the same document and a query
// happily matches the previous test's markup.
afterEach(cleanup);
