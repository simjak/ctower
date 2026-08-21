import type { ComponentKind, CompanyBundleResource, VersionedComponent } from "@ctower/client";
import { canonicalDigest } from "./digest";

/**
 * Authoring a component from the browser.
 *
 * Everything a `VersionedComponent` carries is either the payload's own or
 * fixed by the contract: revision 1 because nothing minted here has a
 * predecessor, `published` because the wizard is putting it into service, and
 * a digest computed the same way the kernel computes it.
 *
 * The provenance says where it came from, honestly. An authored pack names the
 * file it was read out of; these were typed into this wizard, and the record
 * says so rather than borrowing a path that does not exist.
 */
export interface Authored {
  readonly kind: ComponentKind;
  readonly schemaRef: string;
  readonly payload: Readonly<Record<string, unknown>> & { readonly key: string };
}

export function mint(authored: Authored, tenant: string): VersionedComponent {
  const digest = canonicalDigest(authored.payload);
  return {
    compatibility: { ctower: ">=0.0.0,<1.0.0", requires: [] },
    content_digest: digest,
    key: authored.payload.key,
    kind: authored.kind,
    lifecycle: "published",
    payload_ref: `object:${digest}`,
    provenance: [{ digest, kind: "authored", source: "ctower-web/first-run" }],
    revision: 1,
    schema: "ctower.versioned-component/v1",
    schema_ref: authored.schemaRef,
    scope: { project: null, tenant },
    supersedes: null,
  };
}

export function resourceOf(authored: Authored, tenant: string): CompanyBundleResource {
  return { component: mint(authored, tenant), payload: authored.payload };
}
