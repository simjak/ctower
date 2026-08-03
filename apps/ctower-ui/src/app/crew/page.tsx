import { redirect } from "next/navigation";

/**
 * `/crew` with no name.
 *
 * There is no crew index to build: Org already *is* the list of every crew
 * alive on the fleet, with the filters and the counts, and a second roster here
 * would be one more page to keep in step with it. So a bare `/crew` goes there
 * rather than answering 404 to a URL an operator can reasonably type.
 */
export default function CrewIndex(): never {
  redirect("/team");
}
