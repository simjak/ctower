# Changelog

## [0.2.1](https://github.com/simjak/ctower/compare/v0.2.0...v0.2.1) (2026-07-29)


### Bug Fixes

* **migrations:** adopt existing databases with a migration ledger ([#75](https://github.com/simjak/ctower/issues/75)) ([b4e1f66](https://github.com/simjak/ctower/commit/b4e1f66c0629c476a7a3813a8af70e4ec3aa46df))

## [0.2.0](https://github.com/simjak/ctower/compare/v0.1.1...v0.2.0) (2026-07-29)


### Features

* make first-day ticket creation and source lookup usable ([#66](https://github.com/simjak/ctower/issues/66)) ([4c1c6e9](https://github.com/simjak/ctower/commit/4c1c6e9822a08fb3066b2a09b0d1f8ad315f19c1))

## [0.1.1](https://github.com/simjak/ctower/compare/v0.1.0...v0.1.1) (2026-07-28)


### Bug Fixes

* **release:** enforce post-release pre-1.0 policy ([#76](https://github.com/simjak/ctower/issues/76)) ([b583088](https://github.com/simjak/ctower/commit/b583088641f007491779c7f36141807cd138e6ce))

## 0.1.0 (2026-07-28)


### Features

* **access:** implement first-tenant bootstrap ([eb9353d](https://github.com/simjak/ctower/commit/eb9353d5a08274b065c6be0014e6f058dfc39f90))
* add deterministic control loops ([#23](https://github.com/simjak/ctower/issues/23)) ([279624b](https://github.com/simjak/ctower/commit/279624be5564c4a4858813c96b8adf0a8cd68eb5))
* add durable task board vertical ([#20](https://github.com/simjak/ctower/issues/20)) ([65718f5](https://github.com/simjak/ctower/commit/65718f5a27e938cf352525a82e24437f22cba4cc))
* add first durable ticket walking slice ([7c48c67](https://github.com/simjak/ctower/commit/7c48c67abce7c83adf09a950fa8d67238841c83b))
* add I1 trust-spine fixture ([bf2ffb8](https://github.com/simjak/ctower/commit/bf2ffb851ab31c0fb1e32792ca1230e38b66ba1e))
* add persistent shadow runtime ([#60](https://github.com/simjak/ctower/issues/60)) ([20cf29a](https://github.com/simjak/ctower/commit/20cf29a486529892f71e61e29e0e9f644bbddfaf))
* add protected CLI and CompanyBundle ([f4081b1](https://github.com/simjak/ctower/commit/f4081b1739d4a586d2be925b76c314208eeb598d))
* assemble I1.7B dogfood candidate ([#34](https://github.com/simjak/ctower/issues/34)) ([79e292e](https://github.com/simjak/ctower/commit/79e292e437457f92bb6a39bfbfdb2a3a62146529))
* **cli:** add online durable ticket tracer ([59fc062](https://github.com/simjak/ctower/commit/59fc0625762b94531794b7a063c97be848f3aa51))
* **contracts:** scaffold durable ticket slice ([bb531a5](https://github.com/simjak/ctower/commit/bb531a5b8d0c6e8a4b3af76008304af719703e29))
* durable thread-first intake ([#54](https://github.com/simjak/ctower/issues/54)) ([7111520](https://github.com/simjak/ctower/commit/711152066a9f21c0ffa092b91515f3339d5751a3))
* establish the public L0 foundation ([#2](https://github.com/simjak/ctower/issues/2)) ([6d3b7ba](https://github.com/simjak/ctower/commit/6d3b7ba308d9c3ed85f45edd8cce80115b994ef5))
* implement proof-gated workflow slice ([#16](https://github.com/simjak/ctower/issues/16)) ([e3b6840](https://github.com/simjak/ctower/commit/e3b684038331e0855e4f57a98d17e1fd76be2d25))
* **record:** add CP3-C backup and restore checkpoint ([244ff0f](https://github.com/simjak/ctower/commit/244ff0fd2a49e7c94256a5e5ae077ea516d670bd))
* **record:** add replay-safe off-host durability acknowledgement authority ([#22](https://github.com/simjak/ctower/issues/22)) ([df3a783](https://github.com/simjak/ctower/commit/df3a783e8f47b66607821b733120b5af361836ba))
* **work:** add durable ticket creation and reads ([88f2257](https://github.com/simjak/ctower/commit/88f2257d97a0e1fb07542491cb7e7b7d93101b39))
* **work:** enforce atomic custody transfer ([cb3bc87](https://github.com/simjak/ctower/commit/cb3bc87e87e0f05f22da1e36848cec24d2846795))


### Bug Fixes

* close increment-1 cutover trust gaps ([#26](https://github.com/simjak/ctower/issues/26)) ([abcd709](https://github.com/simjak/ctower/commit/abcd709ed91acc5e6219afb1c64b97c505ddb00d))
* **codegen:** derive client and prove process boundary ([75acd8f](https://github.com/simjak/ctower/commit/75acd8f37d410a3da71e16f91625d36351dfa5eb))
* **codegen:** execute authored HTTP constraints ([3480771](https://github.com/simjak/ctower/commit/34807719aceace125e8d9155de388d96869495d1))
* declare authority denial responses ([3331e9c](https://github.com/simjak/ctower/commit/3331e9cc81856ebec69fd0e8637ece2cbb6520cd))
* **policy:** make record boundaries non-waivable ([733bec6](https://github.com/simjak/ctower/commit/733bec63b9f9142d238d90fcc4ebe3f5884d8540))
* **record:** close durable authority invariants ([db05979](https://github.com/simjak/ctower/commit/db05979caa279e9af26e98e529723c3dd8ed795c))
* **record:** enforce kernel persistence boundary ([6a81191](https://github.com/simjak/ctower/commit/6a81191bf545c2c280d1875643b7eaa642ce88f8))
* **record:** validate event authority before hashing ([a5cdbd2](https://github.com/simjak/ctower/commit/a5cdbd252679eb25ec3f5ce81c5f3e191b36f7af))
* **release:** assert first proposal policy ([#69](https://github.com/simjak/ctower/issues/69)) ([089beb5](https://github.com/simjak/ctower/commit/089beb54585f1ea93fd4e72e23c61a1506fb109c))
* **release:** preserve pre-1.0 first proposal ([#41](https://github.com/simjak/ctower/issues/41)) ([4dcbf79](https://github.com/simjak/ctower/commit/4dcbf798eb5802acd3f09e16af368546ea8a1794))
* **telemetry:** record redacted auth denials ([fff62ab](https://github.com/simjak/ctower/commit/fff62aba49d25eddaa7b16efaa827469ab958101))
* **verify:** fail closed on inner recipe failures ([#56](https://github.com/simjak/ctower/issues/56)) ([d4f3715](https://github.com/simjak/ctower/commit/d4f371531e28218ca2a44201e2483918b583c615))
* **verify:** own Secret Service verifier process lifecycle ([#46](https://github.com/simjak/ctower/issues/46)) ([d068b9a](https://github.com/simjak/ctower/commit/d068b9aa6a480e0163d8bc9326790324163105bf))

## Changelog

ctower has not published a version yet. Release Please will add release notes here from
the Conventional Commit titles merged into `main`.

Published releases are immutable. Corrections appear in a newer version rather than by
rewriting an existing tag or release.
