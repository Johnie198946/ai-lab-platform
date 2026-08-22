import assert from "node:assert/strict";
import test from "node:test";

import { isShowroomAccount, SHOWROOM_CONTROLLER_PATH } from "../src/auth/entryRoute.js";

test("showroom demo account always resolves as a showroom identity", () => {
  assert.equal(isShowroomAccount({ username: "showroom_demo" }), true);
  assert.equal(SHOWROOM_CONTROLLER_PATH, "/architect");
});

test("showroom roles are accepted without coupling routing to one username", () => {
  assert.equal(isShowroomAccount({ username: "visitor", roles: ["showroom"] }), true);
  assert.equal(isShowroomAccount({ username: "visitor", roles: [{ code: "showroom_controller" }] }), true);
});

test("ordinary accounts remain on the normal protected workspace", () => {
  assert.equal(isShowroomAccount({ username: "operator", roles: ["admin"] }), false);
  assert.equal(isShowroomAccount(null), false);
});
