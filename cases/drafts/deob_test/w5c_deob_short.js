function w_0x5c3140(_0x41676a, _0x3f9548, _0x39b0b8) {
    function _0x467cb0(_0x174e0d, _0x4ea737) {
      var _0x3ed868 = parseInt(_0x174e0d.slice(_0x4ea737, _0x4ea737 + 2), 16);
      if (_0x3ed868 >>> 7 == 0) {
        return [1, _0x3ed868];
      } else if (_0x3ed868 >>> 6 == 2) {
        _0x3ed868 = (_0x3ed868 & 63) << 8;
        return [2, _0x3ed868 += parseInt(_0x174e0d.slice(_0x4ea737 + 2, _0x4ea737 + 4), 16)];
      } else {
        _0x3ed868 = (_0x3ed868 & 63) << 16;
        return [3, _0x3ed868 += parseInt(_0x174e0d.slice(_0x4ea737 + 2, _0x4ea737 + 6), 16)];
      }
    }
    var _0x450bf1;
    var _0x55d729 = 0;
    var _0x26f45f = [];
    var _0x408609 = [];
    var _0x5e254d = parseInt(_0x41676a.slice(0, 8), 16);
    var _0x56844b = parseInt(_0x41676a.slice(8, 16), 16);
    if (_0x5e254d !== 1213091658 || _0x56844b !== 1077891651) {
      throw new Error("mhe");
    }
    if (parseInt(_0x41676a.slice(16, 18), 16) !== 0) {
      throw new Error("ve");
    }
    for (_0x450bf1 = 0; _0x450bf1 < 4; ++_0x450bf1) {
      _0x55d729 += (parseInt(_0x41676a.slice(24 + _0x450bf1 * 2, 26 + _0x450bf1 * 2), 16) & 3) << _0x450bf1 * 2;
    }
    var _0x537efa = parseInt(_0x41676a.slice(32, 40), 16);
    var _0x3d66d8 = parseInt(_0x41676a.slice(48, 56), 16) * 2;
    for (_0x450bf1 = 56; _0x450bf1 < _0x3d66d8 + 56; _0x450bf1 += 2) {
      _0x26f45f.push(parseInt(_0x41676a.slice(_0x450bf1, _0x450bf1 + 2), 16));
    }
    var _0x50f001 = _0x3d66d8 + 56;
    var _0x23f32e = parseInt(_0x41676a.slice(_0x50f001, _0x50f001 + 4), 16);
    _0x50f001 += 4;
    _0x450bf1 = 0;
    for (; _0x450bf1 < _0x23f32e; ++_0x450bf1) {
      var _0x37a7c1 = _0x467cb0(_0x41676a, _0x50f001);
      _0x50f001 += _0x37a7c1[0] * 2;
      var _0x13d988 = "";
      for (var _0x4b0c3a = 0; _0x4b0c3a < _0x37a7c1[1]; ++_0x4b0c3a) {
        var _0x49abb4 = _0x467cb0(_0x41676a, _0x50f001);
        _0x13d988 += String.fromCharCode(_0x55d729 ^ _0x49abb4[1]);
        _0x50f001 += _0x49abb4[0] * 2;
      }
      _0x408609.push(_0x13d988);
    }
    return _0x408609;}