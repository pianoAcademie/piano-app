import test from 'node:test';
import assert from 'node:assert/strict';
import { allowedAudiences, initialStudent } from '../lib/annual-pricing-selection.ts';

const paul = { id: 'paul', label: 'Paul', kind: 'PROSPECT', audiences: ['CHILD', 'TEEN'] };
const adult = { id: 'adult', label: 'Adulte', kind: 'CLIENT', audiences: ['ADULT'] };
const initiation = { id: 'initiation', title: 'Initiation', quantity: '31', audiences: ['CHILD'] };
const mixed = { id: 'mixed', title: 'Cours ado/adultes', quantity: '32', audiences: ['TEEN', 'ADULT'] };
test('unique prospect selected without requiring a client account', () => assert.equal(initialStudent([paul]), 'paul'));
test('obsolete reviewed identity not retained', () => assert.equal(initialStudent([paul], 'old-client'), 'paul'));
test('parent quote requires explicit choice when multiple students', () => assert.equal(initialStudent([paul, adult]), ''));
test('initiation and awakening only allow child category', () => assert.deepEqual(allowedAudiences(paul, [initiation]), ['CHILD']));
test('mixed course distinguishes teen from adult', () => {
  assert.deepEqual(allowedAudiences(paul, [mixed]), ['TEEN']);
  assert.deepEqual(allowedAudiences(adult, [mixed]), ['ADULT']);
});
test('invalid adult/child course combination cannot be confirmed', () => assert.deepEqual(allowedAudiences(adult, [initiation]), []));
test('incompatible course categories require review, not a wrong discount', () => assert.deepEqual(allowedAudiences(paul, [initiation, mixed]), []));
test('no student selected means no inferred category', () => assert.deepEqual(allowedAudiences(undefined, [mixed]), []));
