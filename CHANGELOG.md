# Changelog

## [1.1.4](https://github.com/canonical/glauth-k8s-operator/compare/v1.1.3...v1.1.4) (2025-12-11)


### Bug Fixes

* return `None` when `bind_password` secret is inaccessible to requirer ([db0b8fb](https://github.com/canonical/glauth-k8s-operator/commit/db0b8fb2435ef2eb302c864b602823a19873ca2e))
* return `None` when `bind_password` secret is inaccessible to requirer ([#205](https://github.com/canonical/glauth-k8s-operator/issues/205)) ([cd5e07f](https://github.com/canonical/glauth-k8s-operator/commit/cd5e07f5112920e39d4ff15f61a7adb70beb17eb))

## [1.1.3](https://github.com/canonical/glauth-k8s-operator/compare/v1.1.2...v1.1.3) (2025-07-30)


### Bug Fixes

* add pod resource constraints ([3b91894](https://github.com/canonical/glauth-k8s-operator/commit/3b918942b1985055408dabf1f8f2eb4814df0d1f))
* compare config file against cm ([0b52bd0](https://github.com/canonical/glauth-k8s-operator/commit/0b52bd0a6f1cde7f070baf60682aec4c87e56239))
* do not restart service if config did not change ([7cd4a8f](https://github.com/canonical/glauth-k8s-operator/commit/7cd4a8f0753c8c01c4b092f70957a5aee9152f7d))
* fix constraint ([dfaeb57](https://github.com/canonical/glauth-k8s-operator/commit/dfaeb576b6a949690326ee10b3ecfb39e23d570e))
* handle update_status ([8c7db47](https://github.com/canonical/glauth-k8s-operator/commit/8c7db471e444db2883aea0d51cfdad4af35ee288))
* set default for var.constraints ([ced318f](https://github.com/canonical/glauth-k8s-operator/commit/ced318f4a459fcef87c752233bb9df21f64017a1))
* set default for var.constraints ([424363d](https://github.com/canonical/glauth-k8s-operator/commit/424363d530ee24e09f856602b8dda47db489e581))
* update charm dependent libs ([0599a64](https://github.com/canonical/glauth-k8s-operator/commit/0599a645542ea392bbb7856eb53eb7cb102640b6))

## [1.1.2](https://github.com/canonical/glauth-k8s-operator/compare/v1.1.1...v1.1.2) (2025-05-05)


### Bug Fixes

* bump `upstream-source` for oci-image to 2.4.0 ([98af110](https://github.com/canonical/glauth-k8s-operator/commit/98af110e5589fc86ff3b0ebaeee14fd575828578))

## [1.1.1](https://github.com/canonical/glauth-k8s-operator/compare/v1.1.0...v1.1.1) (2025-04-02)


### Bug Fixes

* address CVEs ([3ff2442](https://github.com/canonical/glauth-k8s-operator/commit/3ff24425d2c61d87aab836e6573dacbad6e8e8ae)), closes [#124](https://github.com/canonical/glauth-k8s-operator/issues/124)

## [1.1.0](https://github.com/canonical/glauth-k8s-operator/compare/v1.0.1...v1.1.0) (2025-03-27)


### Features

* add terraform module ([4351fc9](https://github.com/canonical/glauth-k8s-operator/commit/4351fc9b8cdfc1a5e2ea08fc7385391671a285e2))
* add the terraform module ([248f37f](https://github.com/canonical/glauth-k8s-operator/commit/248f37f8e5a17db45aaee64dcc6679d73615a279))


### Bug Fixes

* fix the lint ci ([594a7bc](https://github.com/canonical/glauth-k8s-operator/commit/594a7bc57c09b50f44cbd183c712b31a45a22d5f))
* fix the lint ci ([6cb1815](https://github.com/canonical/glauth-k8s-operator/commit/6cb1815b2ffa19a6cd156e5987dca28f97905bd2))

## [1.0.1](https://github.com/canonical/glauth-k8s-operator/compare/v1.0.0...v1.0.1) (2025-03-14)


### Bug Fixes

* add `trust = true` to tf module ([825c095](https://github.com/canonical/glauth-k8s-operator/commit/825c095067c28fb4225ef8535af33ce6b1bca999))
* add `trust = true` to tf module ([a75205c](https://github.com/canonical/glauth-k8s-operator/commit/a75205cc32762c3d1d92e8d967ab25ffd0264ab9))
* Write ldaps_urls only if ldaps_enabled ([d324705](https://github.com/canonical/glauth-k8s-operator/commit/d32470529b14381c1f76f5ea22ac1982fa6dbe1b))
* Write ldaps_urls only if ldaps_enabled ([886e12b](https://github.com/canonical/glauth-k8s-operator/commit/886e12b1b158fdff6686db14948cbecc50376068))

## 1.0.0 (2025-03-10)


### Features

* add `anonymousdse_enabled` config option ([c16ed41](https://github.com/canonical/glauth-k8s-operator/commit/c16ed415af578d410418e6284bf00e95092fde46))
* add `anonymousdse_enabled` config option ([62bebc0](https://github.com/canonical/glauth-k8s-operator/commit/62bebc0838c1f295839a32887eea66246d78b8b3))
* add charm tf module for glauth-k8s ([dffd4e3](https://github.com/canonical/glauth-k8s-operator/commit/dffd4e3f6dd53f5ef592529c593fb35db3236257))
* add module for deploying glauth-k8s with terraform ([a90465c](https://github.com/canonical/glauth-k8s-operator/commit/a90465c1f4230fed2b7875b4529551a2940753ba))
* add tf related ignores to .gitignore ([5dcb274](https://github.com/canonical/glauth-k8s-operator/commit/5dcb274e617e749df254adf686c7281872f35a53))
* apply juju secrets to transfer bind account password ([57e4631](https://github.com/canonical/glauth-k8s-operator/commit/57e4631673ca98ee9fb99bc879234efe5699301e))
* apply juju secrets to transfer bind account password ([059e40b](https://github.com/canonical/glauth-k8s-operator/commit/059e40bbafa7388f4076bf5fd9e20706417379ed))
* base draft charm for gauth-k8s, draft charm-lib ([3979fd9](https://github.com/canonical/glauth-k8s-operator/commit/3979fd9c3b4f09302cad0b7e6d797c4bf969cafb))
* basic output of charmcraft init ([ffc8ad5](https://github.com/canonical/glauth-k8s-operator/commit/ffc8ad5b8ff02397e26474ac96316a1c168f1973))
* enable ingress_per_unit for glauth ([7daa7e2](https://github.com/canonical/glauth-k8s-operator/commit/7daa7e22069e7ba7f8858d065ea4e6cded19c779))
* enable StartTLS support ([96a3ea3](https://github.com/canonical/glauth-k8s-operator/commit/96a3ea31db388f811f4cdb2ec30a7acbaf8bfc3e))
* enable StartTLS support ([b127f0c](https://github.com/canonical/glauth-k8s-operator/commit/b127f0c2390204c6dc47c335dfc9929db907dabb))
* glauth-auxiliary interface integration ([9a08e17](https://github.com/canonical/glauth-k8s-operator/commit/9a08e17f73dddf952fdea422d0e65ce07dfd6315))
* IAM-286 initial commits for charm base ([6664814](https://github.com/canonical/glauth-k8s-operator/commit/6664814b87f89a5662c388911629d8feae4c04d4))
* IAM-286 preliminary commit for charm base ([#15](https://github.com/canonical/glauth-k8s-operator/issues/15)) ([6664814](https://github.com/canonical/glauth-k8s-operator/commit/6664814b87f89a5662c388911629d8feae4c04d4))
* initial version of the ldap interface ([#16](https://github.com/canonical/glauth-k8s-operator/issues/16)) ([5f18a7e](https://github.com/canonical/glauth-k8s-operator/commit/5f18a7ee79518866716abb9d1e47251d47048203))
* integration with tls-certificates interface and certificate-transfer interface ([e654260](https://github.com/canonical/glauth-k8s-operator/commit/e6542602aa4745438a90851b739f81e5abc6662d))
* ldap & auxiliary interface integration and some improvements ([20ca07e](https://github.com/canonical/glauth-k8s-operator/commit/20ca07e007aea05bcfad766e25fee7492a92a0ee))
* ldap interface integration in the glauth-k8s ([5ee495c](https://github.com/canonical/glauth-k8s-operator/commit/5ee495c2b183571ac00bef45768759fe8fe683f2))
* Support for LDAPS ([4245be6](https://github.com/canonical/glauth-k8s-operator/commit/4245be6795ad6b0178a48dee50c7780c2e5b2db0))
* Support LDAPS ([35d37f2](https://github.com/canonical/glauth-k8s-operator/commit/35d37f29dd46052ab0249e0e21e2c3f6e932400a))
* tls-certificates & certificate-transfer interface integrations ([4d96a5a](https://github.com/canonical/glauth-k8s-operator/commit/4d96a5ac768a68b25fda5f57d78b034d05054ee4))
* update the ldap juju interface library ([#17](https://github.com/canonical/glauth-k8s-operator/issues/17)) ([19441a5](https://github.com/canonical/glauth-k8s-operator/commit/19441a53658b399dbc496d76d842496c96965e20))


### Bug Fixes

* accommodate the ldaps ingress ([5023c88](https://github.com/canonical/glauth-k8s-operator/commit/5023c8845f1fa704c64af7ae5b1ef2c4bf93c9e5))
* add integration with ldap provider ([63e9a44](https://github.com/canonical/glauth-k8s-operator/commit/63e9a44f02f1da56eac8c8f0fe9f7ff82837534a))
* add relations method to ldap lib ([4fb58b5](https://github.com/canonical/glauth-k8s-operator/commit/4fb58b50997f3f11202057de472646cf0d43203a))
* add support for pydantic v1 ([bb2bbb0](https://github.com/canonical/glauth-k8s-operator/commit/bb2bbb0c88915eeca88eb88c76a5668efd590518))
* default passwords to "" ([b6de324](https://github.com/canonical/glauth-k8s-operator/commit/b6de324a10f565df3851fffc1c68a50e70e59630)), closes [#55](https://github.com/canonical/glauth-k8s-operator/issues/55)
* default to k8s service for hostname ([ed3ef0a](https://github.com/canonical/glauth-k8s-operator/commit/ed3ef0a978ba68267e94b1ecdf4de1a10f770cfd))
* drop off the CertHandler ([d8102cb](https://github.com/canonical/glauth-k8s-operator/commit/d8102cbdbbeb6e0280560509546ff766124df208))
* drop off the CertHandler ([080d83e](https://github.com/canonical/glauth-k8s-operator/commit/080d83ec37476bb8b1c5fbe9f09de9476e229971))
* expect single remote ldap ([ae901b4](https://github.com/canonical/glauth-k8s-operator/commit/ae901b47ed03cd90b9fd8b8f0c2eb3379f61eccb))
* expect urls in ldap integration ([9ec1975](https://github.com/canonical/glauth-k8s-operator/commit/9ec19750ac7087ffba5e8d9d5187cc1cce3eb721))
* extend pydantic v1 support to multiple fields ([10f413f](https://github.com/canonical/glauth-k8s-operator/commit/10f413f4be6c335fbff34a0c47b83d28075bc34a))
* fix tests ([694b553](https://github.com/canonical/glauth-k8s-operator/commit/694b553cafe6eae2a03657f7405f2508cd159441))
* fix the ca chain value in the certificate transfer integration ([9c78ee2](https://github.com/canonical/glauth-k8s-operator/commit/9c78ee2878a8cf0cbbc0deec4a8459fc2939292b))
* fix the ca chain value in the certificate transfer integration ([099f16e](https://github.com/canonical/glauth-k8s-operator/commit/099f16e4747b2cd87cca69e7e18d35c30f2635f8))
* fix the ldap requested event initialization ([356c6eb](https://github.com/canonical/glauth-k8s-operator/commit/356c6eb0d23d48c4347adad7162537d462eaa75b))
* fix the ldap requested event initialization ([76fe8c3](https://github.com/canonical/glauth-k8s-operator/commit/76fe8c389b60aedb0662886ef212694d423f93e7))
* **loki-rule:** improve error handling in json parsing ([#23](https://github.com/canonical/glauth-k8s-operator/issues/23)) ([d799515](https://github.com/canonical/glauth-k8s-operator/commit/d799515e9263b7d889885fd2a06179b085ffc427))
* mount cm on pebble_ready ([a323928](https://github.com/canonical/glauth-k8s-operator/commit/a323928e666a40b1c7245c87433945f91fc13721))
* pass remote bind_dn on ldap integration ([3041aff](https://github.com/canonical/glauth-k8s-operator/commit/3041aff411f394c1ebfb25de5404bf1f822611cb))
* properly raise pydantic exception ([eac931a](https://github.com/canonical/glauth-k8s-operator/commit/eac931ad4a901a7c5f2e967d6e9a6350149039ff))
* provide raw password to ldap relation ([1d268cf](https://github.com/canonical/glauth-k8s-operator/commit/1d268cf8a4a59f58be05fe14376e2fe0cc220588))
* refactor the ldap lib ([bef6627](https://github.com/canonical/glauth-k8s-operator/commit/bef6627011e6c720314b8f0f5607900095a15717))
* remove peer relation ([3b3e8b2](https://github.com/canonical/glauth-k8s-operator/commit/3b3e8b2ade11613a614b4af2085a741eb80338a0))
* solve the mounted configmap update delay issue ([53d1467](https://github.com/canonical/glauth-k8s-operator/commit/53d146772efba4e3ae57ddf725ad958a55e9af0f))
* update charm libs ([15bba38](https://github.com/canonical/glauth-k8s-operator/commit/15bba38ee154521072c3861e1549c5529719d719))
* update charm libs ([7133255](https://github.com/canonical/glauth-k8s-operator/commit/71332552724aa4ba49293e51a76e166d1a7fbc1c))
* update tablename ([2674e8c](https://github.com/canonical/glauth-k8s-operator/commit/2674e8c36ed5de26110daa6b1d5f1051d902e48b))
* update tablename ([e9c788d](https://github.com/canonical/glauth-k8s-operator/commit/e9c788d424c632429aeba1dcbfc2fe4c7ace5282))
* update the tls certificate in ingress-per-unit integration ([f95d583](https://github.com/canonical/glauth-k8s-operator/commit/f95d583a463658fc672ec6f084286f862aae17e2))
* update the tls certificate in ingress-per-unit integration ([c7422e4](https://github.com/canonical/glauth-k8s-operator/commit/c7422e45f3236927b00966812c276a5c75553d4f))
* upgrade the data_interface library and adapt the code ([6d5a13f](https://github.com/canonical/glauth-k8s-operator/commit/6d5a13f7df6469e21bfb14ed9117a69acda275b9))
* use cert_handler v1 ([b941d3c](https://github.com/canonical/glauth-k8s-operator/commit/b941d3c05151ec3af4258a3132ce071cbfc883b2))
