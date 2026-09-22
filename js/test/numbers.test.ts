import { strict as assert } from 'node:assert';
import { describe, it } from 'node:test';
import { fixed, grouped, signed } from '../src/format/numbers.js';

/**
 * The report prints numbers two ways, and the two round differently. A reader
 * comparing a probability with its trigger would otherwise be reading the
 * difference between two rounding rules
 */
describe('the two ways a number is printed', () => {
    it('rounds a printed probability half to even, on the value the double holds', () => {
        assert.equal(fixed(0.705, 2), '0.70');
        assert.equal(fixed(0.715, 2), '0.71');
        assert.equal(fixed(2.5, 0), '2');
        assert.equal(fixed(3.5, 0), '4');
        assert.equal(fixed(0.25, 1), '0.2');
        assert.equal(fixed(1.005, 2), '1.00');
    });

    it('rounds a grouped number half away from zero, on the shortest decimal', () => {
        assert.equal(grouped(0.705, 2), '0.71');
        assert.equal(grouped(0.715, 2), '0.72');
        assert.equal(grouped(0.725, 2), '0.73');
        assert.equal(grouped(2.5, 0), '3');
        assert.equal(grouped(1234567), '1,234,567');
    });

    it('prints a sign on a delta, and no sign on a negative zero', () => {
        assert.equal(signed(0.0015, 3), '+0.002');
        assert.equal(signed(-0.0005, 3), '-0.001');
        assert.equal(signed(-0, 3), '+0.000');
        assert.equal(grouped(-0, 2), '0.00');
    });
});
