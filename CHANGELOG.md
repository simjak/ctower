# Changelog

## [0.9.0](https://github.com/simjak/ctower/compare/v0.8.1...v0.9.0) (2026-08-07)


### Features

* add native agent inbox ([#336](https://github.com/simjak/ctower/issues/336)) ([8987df4](https://github.com/simjak/ctower/commit/8987df43f18d6089c1721b3db478b77d0aa4d418))

## [0.8.1](https://github.com/simjak/ctower/compare/v0.8.0...v0.8.1) (2026-08-07)


### Bug Fixes

* **auth:** render unavailable login page ([#342](https://github.com/simjak/ctower/issues/342)) ([5b8a9f5](https://github.com/simjak/ctower/commit/5b8a9f5095d0a71b00277b7ce00de601ca5b8b44))
* **ui:** render board card context and contain mobile lanes ([#340](https://github.com/simjak/ctower/issues/340)) ([e353907](https://github.com/simjak/ctower/commit/e3539074460ffd55286c75d1209027da91295c34))

## [0.8.0](https://github.com/simjak/ctower/compare/v0.7.4...v0.8.0) (2026-08-06)


### Features

* **access:** provider-agnostic OIDC two-plane login scaffold (gh[#214](https://github.com/simjak/ctower/issues/214)) ([#324](https://github.com/simjak/ctower/issues/324)) ([280ce5f](https://github.com/simjak/ctower/commit/280ce5f60a13ac66eb6915640196b24134de3705))
* **board:** wire INV-66/67 context-set fields into the Board card ([#326](https://github.com/simjak/ctower/issues/326)) ([4f52c8e](https://github.com/simjak/ctower/commit/4f52c8e705d5c894cea85c33e71ddcb6df92dbf0))
* **checks:** add async subprocess vocabulary to the process inventory ([#309](https://github.com/simjak/ctower/issues/309)) ([80fca4f](https://github.com/simjak/ctower/commit/80fca4f790aaf63864dfc3ab45ace937e476802d))
* **cli:** ctowerctl installs anywhere and finds its instance ([#286](https://github.com/simjak/ctower/issues/286)) ([f0ac4ff](https://github.com/simjak/ctower/commit/f0ac4ff1469e9c048919ce2d9d671afe46106a3f)), closes [#193](https://github.com/simjak/ctower/issues/193)
* **contracts:** bind verdict_id + candidate_digest per criterion row (evidence-manifest/v2) ([#295](https://github.com/simjak/ctower/issues/295)) ([081137b](https://github.com/simjak/ctower/commit/081137bad0c8a141855f6e6366f152fbaa58d5b2)), closes [#174](https://github.com/simjak/ctower/issues/174)
* **events:** publish the project-scoped typed event feed (CT-I1-012) ([#299](https://github.com/simjak/ctower/issues/299)) ([bad5043](https://github.com/simjak/ctower/commit/bad5043669f651fe347929e18ac9337ac1d1bc84)), closes [#186](https://github.com/simjak/ctower/issues/186)
* **ui:** wire the live terminal into the crew profile and seat aggregate ([#322](https://github.com/simjak/ctower/issues/322)) ([abd2f93](https://github.com/simjak/ctower/commit/abd2f935189de359d2b22d302377f3d12e9c10a3))
* **ui:** wire the promised cross-project portfolio view (gh[#319](https://github.com/simjak/ctower/issues/319) direction-a) ([#327](https://github.com/simjak/ctower/issues/327)) ([26651e3](https://github.com/simjak/ctower/commit/26651e3bed27bd5cc9035f28e44ddbddd92c1433))


### Bug Fixes

* **checks:** bound the Playwright gate's process wait with a deadline ([#307](https://github.com/simjak/ctower/issues/307)) ([1ba9f16](https://github.com/simjak/ctower/commit/1ba9f16097b5cceb5c46763cc2f97a4eb72f531d)), closes [#114](https://github.com/simjak/ctower/issues/114)
* **checks:** exclude interpreter bytecode from generated inventory ([#298](https://github.com/simjak/ctower/issues/298)) ([15e298c](https://github.com/simjak/ctower/commit/15e298c9a67b6c8b1513002192d1f04296e3236c)), closes [#94](https://github.com/simjak/ctower/issues/94)
* **checks:** fail closed on nested star-imports and conditional/mutated __all__ ([#304](https://github.com/simjak/ctower/issues/304)) ([b0feae7](https://github.com/simjak/ctower/commit/b0feae72afbfb1c9d4d9390f4bd1688abb3dd1a7)), closes [#1](https://github.com/simjak/ctower/issues/1)
* **ci:** render observe-mode landing-boundary as neutral, not FAILURE ([#283](https://github.com/simjak/ctower/issues/283)) ([a87958c](https://github.com/simjak/ctower/commit/a87958cb372c93227dca1d1eac120813e6442405)), closes [#277](https://github.com/simjak/ctower/issues/277)
* clear gh[#165](https://github.com/simjak/ctower/issues/165)'s D5 (delete rowcount) + D8 (broken suite collection) ([#311](https://github.com/simjak/ctower/issues/311)) ([a332759](https://github.com/simjak/ctower/commit/a33275969011a089189267260cbbb242f5b58e53))
* **cli:** control health fails loud instead of masking unknown state ([#306](https://github.com/simjak/ctower/issues/306)) ([5b26837](https://github.com/simjak/ctower/commit/5b268370929db23cc00b17cf2df7a743f4a5be9a))
* **cli:** derive --command-id for every mutation, not just three ([#325](https://github.com/simjak/ctower/issues/325)) ([a400f28](https://github.com/simjak/ctower/commit/a400f286a16260c5c39282a8158ba1e5db03217f))
* **contracts:** lock evidence-manifest/v1's shape and version it going forward ([#287](https://github.com/simjak/ctower/issues/287)) ([f3dc555](https://github.com/simjak/ctower/commit/f3dc55508dddac9345bcbe0aed88818b4d84fb0d))
* **contracts:** unfreeze corpus cardinality in migration schemas ([#293](https://github.com/simjak/ctower/issues/293)) ([e08931c](https://github.com/simjak/ctower/commit/e08931cb0e073549575630d187442ba464f8c941))
* **dev-runtime:** readback-verify forced container removal ([#297](https://github.com/simjak/ctower/issues/297)) ([74064f6](https://github.com/simjak/ctower/commit/74064f608f63a32f0dcc2d19f31d5e25c6324495)), closes [#70](https://github.com/simjak/ctower/issues/70)
* **dev-runtime:** reconcile orphaned runtime-replacement directories ([#321](https://github.com/simjak/ctower/issues/321)) ([b0f5f92](https://github.com/simjak/ctower/commit/b0f5f921101c818b9908321d3e017787595ca682)), closes [#127](https://github.com/simjak/ctower/issues/127)
* **dev-runtime:** remove the primary initializer on a readiness-deadline miss ([#301](https://github.com/simjak/ctower/issues/301)) ([cfa621b](https://github.com/simjak/ctower/commit/cfa621bafa47c1993de857fdf6f23895f2787d3e)), closes [#72](https://github.com/simjak/ctower/issues/72)
* **dev-runtime:** retire the predecessor instead of deleting it before commit ([#308](https://github.com/simjak/ctower/issues/308)) ([dbd9dc8](https://github.com/simjak/ctower/commit/dbd9dc812a4dfa661be86b86d6e870431e74ece6)), closes [#121](https://github.com/simjak/ctower/issues/121)
* **dev-runtime:** surface the candidate interpreter's stderr on a preflight crash ([#315](https://github.com/simjak/ctower/issues/315)) ([45e8d98](https://github.com/simjak/ctower/commit/45e8d985340896388053e0339c9d2d52841a88cc))
* gate the credential path on schema generation 0039 (gh[#259](https://github.com/simjak/ctower/issues/259)) ([#296](https://github.com/simjak/ctower/issues/296)) ([a444cff](https://github.com/simjak/ctower/commit/a444cff787453b4a6f89821684f16fe358f6d160))
* **kernel:** bound ambiguous-commit recovery with backoff and cap ordinary-mode statement time ([#302](https://github.com/simjak/ctower/issues/302)) ([2f385fa](https://github.com/simjak/ctower/commit/2f385fafc7bd8f3e1ccfec4230cb44534fd3f6e8)), closes [#88](https://github.com/simjak/ctower/issues/88)
* **kernel:** derive Board project-source event kinds from the fold dispatch ([#284](https://github.com/simjak/ctower/issues/284)) ([e66f5b3](https://github.com/simjak/ctower/commit/e66f5b302de02cc1d68f74eb1e21fec76891b738)), closes [#204](https://github.com/simjak/ctower/issues/204)
* **kernel:** index Board source-reference lookup instead of Python-filtering a full fetch ([#310](https://github.com/simjak/ctower/issues/310)) ([37c6dda](https://github.com/simjak/ctower/commit/37c6dda028fda5fd8aecc07ac18799d5f3327baa))
* **kernel:** join fixed_operation_results into the Routine pending-jobs count ([#316](https://github.com/simjak/ctower/issues/316)) ([ca10d69](https://github.com/simjak/ctower/commit/ca10d69a695c8c532d4d75529e19d39abd2ede05))
* **kernel:** read the active-checkpoint snapshot once per reconcile ([#313](https://github.com/simjak/ctower/issues/313)) ([cb53231](https://github.com/simjak/ctower/commit/cb532316f0e9e4a5b518bed70b21b78b491cd1eb)), closes [#165](https://github.com/simjak/ctower/issues/165)
* **kernel:** scope checkpoint materialization completeness per project ([#285](https://github.com/simjak/ctower/issues/285)) ([532c130](https://github.com/simjak/ctower/commit/532c130d98db4d689cc6e19ebd03c1c398d8081f))
* **migration:** name the checkpoint expectation a cutover refusal fails on ([#292](https://github.com/simjak/ctower/issues/292)) ([962d541](https://github.com/simjak/ctower/commit/962d541012599a98a13f9e56330f9ab3987229b1)), closes [#183](https://github.com/simjak/ctower/issues/183)
* **migration:** split _pass_two_sql.py's graph projection (D2) + document empty-signed-set fallback (D5) ([#312](https://github.com/simjak/ctower/issues/312)) ([12008b4](https://github.com/simjak/ctower/commit/12008b4780724c80007d4105ec2b791f8534bfd8))
* **record:** add the column statistics target to the adoption fingerprint ([#305](https://github.com/simjak/ctower/issues/305)) ([84792d2](https://github.com/simjak/ctower/commit/84792d2d02b0203b88eef67ca5b454f420439ee4)), closes [#80](https://github.com/simjak/ctower/issues/80)
* **tests:** redact secret-shaped values from pytest failure output ([#294](https://github.com/simjak/ctower/issues/294)) ([474eea3](https://github.com/simjak/ctower/commit/474eea37fd3b0bd23767d9cd467b709044485807)), closes [#290](https://github.com/simjak/ctower/issues/290)
* **ui:** brand the Inbox info chip and drop the kept-unkept board promise ([#323](https://github.com/simjak/ctower/issues/323)) ([360bba9](https://github.com/simjak/ctower/commit/360bba928bda8d3cf71067a9d5e3fa9581be018b))

## [0.7.4](https://github.com/simjak/ctower/compare/v0.7.3...v0.7.4) (2026-08-04)


### Bug Fixes

* **api:** mount bundle routes in development runtime ([#279](https://github.com/simjak/ctower/issues/279)) ([a71be94](https://github.com/simjak/ctower/commit/a71be94919ffc552fc0765f0f35673f29e82fa0f))

## [0.7.3](https://github.com/simjak/ctower/compare/v0.7.2...v0.7.3) (2026-08-04)


### Bug Fixes

* keep bundle read failures typed ([#274](https://github.com/simjak/ctower/issues/274)) ([3c7167a](https://github.com/simjak/ctower/commit/3c7167a6cafd326bb57e5211d05f89dd433bd91a))
* **ui:** never render a 0-of-0 board answer as empty ([#276](https://github.com/simjak/ctower/issues/276)) ([763ded6](https://github.com/simjak/ctower/commit/763ded681c0c0c3222aef68d7b28ed7fd533b0de))

## [0.7.2](https://github.com/simjak/ctower/compare/v0.7.1...v0.7.2) (2026-08-04)


### Bug Fixes

* **deps:** four held bumps via the canonical lock flow + lock-freshness catch — fastapi 0.141.1, uv 0.12.1, ruamel-yaml 0.19.1, ruff 0.16.1 ([#271](https://github.com/simjak/ctower/issues/271)) ([b76e406](https://github.com/simjak/ctower/commit/b76e4068da8f0feee025e517319308cad39d263e))

## [0.7.1](https://github.com/simjak/ctower/compare/v0.7.0...v0.7.1) (2026-08-04)


### Bug Fixes

* **deps:** three held bumps via the canonical lock flow — cryptography 50 (security), uvicorn 0.52, pre-commit 4.6.1 ([#262](https://github.com/simjak/ctower/issues/262)) ([7d64a47](https://github.com/simjak/ctower/commit/7d64a478d8c79e8d15466a11d4540ca48b71171f))

## [0.7.0](https://github.com/simjak/ctower/compare/v0.6.0...v0.7.0) (2026-08-03)


### Features

* **gate:** one required check, two record-backed facts ([#224](https://github.com/simjak/ctower/issues/224)) ([4d238a6](https://github.com/simjak/ctower/commit/4d238a6dfb5cdab6900b415466666c407ae57b6c))
* **intake:** refuse the five prohibited data classes by name ([#222](https://github.com/simjak/ctower/issues/222)) ([3a5e87c](https://github.com/simjak/ctower/commit/3a5e87cec8623db9bcf5c190c503e7095978546a))
* **record:** work sessions become facts the record can prove ([#258](https://github.com/simjak/ctower/issues/258)) ([2a0a98e](https://github.com/simjak/ctower/commit/2a0a98ed81d03aed48f70ef74cbe1bc8ad68a1ce))
* **ui:** one crew in full — the profile behind every roster row ([#234](https://github.com/simjak/ctower/issues/234)) ([83a9bdb](https://github.com/simjak/ctower/commit/83a9bdb39ab78eb61959c93b1eca944e4f902648))
* **ui:** the read-only operator surface over the shadow record ([#207](https://github.com/simjak/ctower/issues/207)) ([f8f73c5](https://github.com/simjak/ctower/commit/f8f73c5bc88b0caec67b6884e8044627ae4c72a0))
* **workflow:** read the authored S7/S8 workflow definition ([#225](https://github.com/simjak/ctower/issues/225)) ([44bcc6e](https://github.com/simjak/ctower/commit/44bcc6e2a05194515976532f8f9709bc15cec8a3))


### Bug Fixes

* **record:** history must not block upgrade — scope migration invariants to the path that can prove them ([#244](https://github.com/simjak/ctower/issues/244)) ([de817c0](https://github.com/simjak/ctower/commit/de817c027d6b56a8a5c8c94e9065bf31ded9db20))
* **record:** render the schema attestation canonically so a re-parse cannot fail it ([#248](https://github.com/simjak/ctower/issues/248)) ([528d38b](https://github.com/simjak/ctower/commit/528d38b2f1d03b1d70519c35371c871a436a6c35))
* **spool:** surface the refusal payload on spool drain ([#256](https://github.com/simjak/ctower/issues/256)) ([5c89151](https://github.com/simjak/ctower/commit/5c89151348745c3d26a80ae2e8ac61d222f6c5bb))
* **ui:** the eight defects QA found by using the board ([#246](https://github.com/simjak/ctower/issues/246)) ([96d3fdc](https://github.com/simjak/ctower/commit/96d3fdc8c8f2b3736422f070384fe9458eb64ad1))

## [0.6.0](https://github.com/simjak/ctower/compare/v0.5.0...v0.6.0) (2026-08-03)


### Features

* **cli:** render stable evidence-backed delivery rows ([#190](https://github.com/simjak/ctower/issues/190)) ([ff96078](https://github.com/simjak/ctower/commit/ff9607883f685033e27c3b0f2383f4c7d58e3573))
* **runtime:** checkpoint, list, and restore verbs for the shadow instance ([#223](https://github.com/simjak/ctower/issues/223)) ([699b9f5](https://github.com/simjak/ctower/commit/699b9f55a6ee12f85a1d875f10cff9f747ed75db))
* **scopes:** isolate three project read models ([#197](https://github.com/simjak/ctower/issues/197)) ([831a264](https://github.com/simjak/ctower/commit/831a26415e9aae1ff6e71845f1409296f861b04a))


### Bug Fixes

* serialize role provisioning across the cluster ([#188](https://github.com/simjak/ctower/issues/188)) ([cf4a313](https://github.com/simjak/ctower/commit/cf4a3136d6f18e9de97017e90155b62ffe3678de))

## [0.5.0](https://github.com/simjak/ctower/compare/v0.4.1...v0.5.0) (2026-08-02)


### Features

* carry the seat facts ([#191](https://github.com/simjak/ctower/issues/191)) ([f41a0f2](https://github.com/simjak/ctower/commit/f41a0f228399345df1031e43fbb0a72e60dee988))
* issue scoped project-seat credentials ([#198](https://github.com/simjak/ctower/issues/198)) ([1c6aba7](https://github.com/simjak/ctower/commit/1c6aba7863cecc80f2e9264e37fc0d1903452883))

## [0.4.1](https://github.com/simjak/ctower/compare/v0.4.0...v0.4.1) (2026-08-01)


### Bug Fixes

* **migration:** follow signed source sets ([#179](https://github.com/simjak/ctower/issues/179)) ([091c4b4](https://github.com/simjak/ctower/commit/091c4b444f48147f55cb2736df71e30328ae9e5a))

## [0.4.0](https://github.com/simjak/ctower/compare/v0.3.1...v0.4.0) (2026-07-31)


### Features

* derive project delivery from active facts ([#160](https://github.com/simjak/ctower/issues/160)) ([4d6149b](https://github.com/simjak/ctower/commit/4d6149b5c4a5fc944ba8e83011750882603e4022))
* **migration:** S4 source-conservation artifacts — exhaustive dispositions, named refusals, mutation-proof conservation ([#172](https://github.com/simjak/ctower/issues/172)) ([26dddbc](https://github.com/simjak/ctower/commit/26dddbc87e337cf35a739b5408ed52ea3ce802c4))
* type the I1 evidence denominator ([#171](https://github.com/simjak/ctower/issues/171)) ([25f07b3](https://github.com/simjak/ctower/commit/25f07b3ecb555bc9f22b944eec6851b1c9c12e38))

## [0.3.1](https://github.com/simjak/ctower/compare/v0.3.0...v0.3.1) (2026-07-30)


### Bug Fixes

* make standby health baseline deterministic ([#154](https://github.com/simjak/ctower/issues/154)) ([423212c](https://github.com/simjak/ctower/commit/423212c18b6b2a6d0ab5326d3f92502583572f3a))

## [0.3.0](https://github.com/simjak/ctower/compare/v0.2.2...v0.3.0) (2026-07-30)


### Features

* **runtime:** add atomic replacement and rollback ([#91](https://github.com/simjak/ctower/issues/91)) ([cabbf68](https://github.com/simjak/ctower/commit/cabbf6871eb9c8518ca48a63fbc750097dd7a2f1))


### Bug Fixes

* **migrations:** serialize role reconciliation ([#87](https://github.com/simjak/ctower/issues/87)) ([b002618](https://github.com/simjak/ctower/commit/b00261866f0965ae3ff70142adfd7d46a60ed3b7))
* **runtime:** preflight checkout entry points ([#107](https://github.com/simjak/ctower/issues/107)) ([24e23e6](https://github.com/simjak/ctower/commit/24e23e667999c86cd397f4929a907fc0c245258b))

## [0.2.2](https://github.com/simjak/ctower/compare/v0.2.1...v0.2.2) (2026-07-30)


### Bug Fixes

* **cli:** make workflow lifecycle reachable ([#84](https://github.com/simjak/ctower/issues/84)) ([4d88a99](https://github.com/simjak/ctower/commit/4d88a9962e06f2ee3325e43cb31ff5036f6ac77d))

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
