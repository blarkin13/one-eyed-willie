// Prints a new Ed25519 signing key for remote-access passes.
//   node cloudflare/yarr/tools/new-pass-key.mjs | npx wrangler secret put PASS_SIGNING_KEY
// Rotation: before replacing it, copy the current key's public half (kty, crv,
// x, kid; never "d") into PASS_PREVIOUS_PUBLIC_JWK so passes already issued
// keep working until they expire (at most an hour).
import {webcrypto} from 'node:crypto';
const pair=await webcrypto.subtle.generateKey({name:'Ed25519'},true,['sign','verify']);
const jwk=await webcrypto.subtle.exportKey('jwk',pair.privateKey);
const kid='yarr-'+new Date().toISOString().slice(0,10)+'-'+Buffer.from(webcrypto.getRandomValues(new Uint8Array(3))).toString('hex');
process.stdout.write(JSON.stringify({kty:jwk.kty,crv:jwk.crv,x:jwk.x,d:jwk.d,kid}));
