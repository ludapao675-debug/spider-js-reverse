var body = [];
var touche_move = {};
var touch_list = [];
var url = "//blackhole.m.jd.com/bypass";
var business_list = ["mlogin", "mregister", "beanGameTopic", "beanGameLLX", "sbeanGameLLX"];
var _webmCurrScript = "storage.360buyimg.com/jsresource/ws_js/gatherInfo.js";
var _webmCallList = [];
var _webmTimer = null;
var _webmReportData = [];
var _webmRegex = /https?:\/\/(.*?(\.js|\.html))\b/;
function _webmReport() {
  try {
    if (!_webmReportData || _webmReportData.length === 0) {
      return;
    }
    var _0x2a75b9 = {};
    var _0x41ffeb;
    if (window.XMLHttpRequest) {
      _0x41ffeb = new XMLHttpRequest();
    } else {
      _0x41ffeb = new ActiveXObject("Microsoft.XMLHTTP");
    }
    _0x41ffeb.open("post", url, true);
    _0x41ffeb.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
    _0x41ffeb.onreadystatechange = function () {
      if (_0x41ffeb.readyState == 4) {
        if (_0x41ffeb.status == 200 || _0x41ffeb.status == 0) {
          try {
            var _0x1ea1cf = _0x41ffeb.responseText;
            if (_0x1ea1cf) {
              var _0x71ace3 = JSON.parse(_0x1ea1cf);
              if (_0x71ace3.code == 0) {
                _webmReportData = [];
              }
            }
          } catch (_0x362f52) {}
        }
      }
    };
    var _0x5474fc = getFingerPrint();
    var _0xbbed42 = _0x5474fc ? _0x5474fc[2] : "";
    _0x2a75b9.appname = "scall_modeH5";
    _0x2a75b9.body = _webmReportData;
    _0x2a75b9.whwswswws = _0xbbed42;
    _0x41ffeb.send("body=" + JSON.stringify(_0x2a75b9));
  } catch (_0x96c733) {}
}
function _webmDispatch(_0x2682bd) {
  _webmReportData.push(_0x2682bd);
  if (_webmTimer) {
    clearTimeout(_webmTimer);
    _webmTimer = null;
  }
  _webmTimer = setTimeout(function () {
    _webmReport();
  }, 1000);
}
function _webmCallStackListener(_0x4ce77d) {
  var _0x1f6b72 = "";
  try {
    if (arguments.callee.caller && arguments.callee.caller.caller) {
      _0x1f6b72 = arguments.callee.caller.caller.name;
      throw new Error();
    }
  } catch (_0x3a79f6) {
    try {
      var _0x1f455e = _0x3a79f6.stack.split("\n");
      if (_0x1f455e && _0x1f455e.length > 1) {
        var _0x5cf049 = 1;
        var _0x166991 = _0x1f455e[_0x5cf049].match(_webmRegex);
        while (_0x166991 && _0x166991.length > 0 && _0x166991[0].indexOf(_webmCurrScript) > -1) {
          _0x5cf049++;
          if (_0x1f455e.length > _0x5cf049) {
            _0x166991 = _0x1f455e[_0x5cf049].match(_webmRegex);
          } else {
            _0x166991 = [];
          }
        }
        if (_0x166991 && _0x166991.length > 0 && _0x166991[0].indexOf(_webmCurrScript) == -1) {
          var _0x189c7d = _0x166991[0];
          var _0x1e9bf0 = false;
          for (var _0x1335d9 = 0; _0x1335d9 < _webmReportData.length; _0x1335d9++) {
            var _0x2c5d4b = _webmReportData[_0x1335d9];
            if (_0x2c5d4b.from == _0x189c7d && _0x2c5d4b.funcName == _0x4ce77d) {
              _0x1e9bf0 = true;
              break;
            }
          }
          if (!_0x1e9bf0) {
            var _0x48da88 = {
              funcName: _0x4ce77d,
              pageUrl: window.location.href,
              from: _0x189c7d,
              caller: _0x1f6b72
            };
            _webmDispatch(_0x48da88);
            if (_webmCallList.indexOf(_0x189c7d) == -1) {
              _webmCallList.push(_0x189c7d);
            }
          }
        }
      }
    } catch (_0x8fc346) {}
  }
}
function sendMessage(_0x2a43e3, _0x52994b) {
  _webmCallStackListener("sendMessage");
  try {
    if (!_0x2a43e3 || _0x2a43e3.length == 0) {
      return;
    }
    var _0x2b9a48 = {};
    var _0x43bdad;
    if (window.XMLHttpRequest) {
      _0x43bdad = new XMLHttpRequest();
    } else {
      _0x43bdad = new ActiveXObject("Microsoft.XMLHTTP");
    }
    _0x43bdad.open("post", url, true);
    _0x43bdad.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
    _0x43bdad.onreadystatechange = function () {
      if (_0x43bdad.readyState == 4) {
        if (_0x43bdad.status == 200 || _0x43bdad.status == 0) {
          try {
            var _0xe4e973 = _0x43bdad.responseText;
            if (_0xe4e973) {
              var _0x4eded0 = JSON.parse(_0xe4e973);
              if (_0x4eded0.code == 0) {
                body = [];
                setStorage("upload_data", body);
              }
            }
          } catch (_0x240e63) {}
        }
      }
    };
    _0x2b9a48.appname = "wireless.safe.m.jd";
    _0x2b9a48.body = _0x2a43e3;
    _0x2b9a48.whwswswws = _0x52994b;
    _0x43bdad.send("body=" + JSON.stringify(_0x2b9a48));
  } catch (_0x4f52c1) {}
}
var upload_data = getStorage("upload_data");
if (upload_data && upload_data.length > 0) {
  try {
    var fingerPrintValue = getFingerPrint();
    var fingerPrint = fingerPrintValue ? fingerPrintValue[2] : "";
    sendMessage(upload_data, fingerPrint);
  } catch (_0x3e4095) {}
}
Date.prototype.WebmFormatTime = function (_0x403e85) {
  try {
    var _0x3f7697 = {
      "M+": this.getMonth() + 1,
      "d+": this.getDate(),
      "h+": this.getHours(),
      "m+": this.getMinutes(),
      "s+": this.getSeconds(),
      "q+": Math.floor((this.getMonth() + 3) / 3),
      S: this.getMilliseconds()
    };
    if (/(y+)/.test(_0x403e85)) {
      _0x403e85 = _0x403e85.replace(RegExp.$1, (this.getFullYear() + "").substr(4 - RegExp.$1.length));
    }
    for (var _0x4a9bc5 in _0x3f7697) {
      if (new RegExp("(" + _0x4a9bc5 + ")").test(_0x403e85)) {
        _0x403e85 = _0x403e85.replace(RegExp.$1, RegExp.$1.length == 1 ? _0x3f7697[_0x4a9bc5] : ("00" + _0x3f7697[_0x4a9bc5]).substr(("" + _0x3f7697[_0x4a9bc5]).length));
      }
    }
    return _0x403e85;
  } catch (_0xdf8aad) {
    return _0x403e85;
  }
};
function in_array(_0x4222f4) {
  _webmCallStackListener("in_array");
  for (var _0xc26c2d = 0; _0xc26c2d < business_list.length; _0xc26c2d++) {
    if (_0x4222f4 === business_list[_0xc26c2d]) {
      return true;
    }
  }
  return false;
}
function getBusinness() {
  _webmCallStackListener("getBusinness");
  try {
    var _0x50faea = document.scripts;
    for (var _0x44e53e = 0; _0x44e53e < _0x50faea.length; _0x44e53e++) {
      if (_0x50faea[_0x44e53e].src.indexOf("jdwebm.js") != -1) {
        return _0x50faea[_0x44e53e].src.split("?")[1].split("=")[1].split("&")[0];
      }
    }
  } catch (_0x3e0cf4) {
    return "";
  }
}
var business_name = getBusinness();
if (in_array(business_name)) {
  document.addEventListener("touchstart", touchStart, false);
  document.addEventListener("touchmove", touchMove, false);
}
function touchStart(_0x8e09c7) {
  _webmCallStackListener("touchStart");
  try {
    var _0x15c802 = {};
    var _0x32f026 = getCookie("pin");
    touche_move.point = [];
    if (!_0x32f026) {
      _0x32f026 = getCookie("pwdt_id");
    }
    var _0x7c9214 = _0x8e09c7.changedTouches[0];
    touche_move.pagename = window.location.href;
    touche_move.eventid = "STouch";
    touche_move.domid = _0x7c9214.target.id;
    touche_move.classname = _0x7c9214.target.className;
    touche_move.business_id = business_name;
    if (touch_list.length != 0) {
      if (touch_list.length <= 5) {
        touche_move.point = touch_list;
      } else {
        touche_move.point.push(touch_list[0]);
        touche_move.point.push(touch_list[Math.floor(touch_list.length / 2) - Math.floor(Math.floor(touch_list.length / 2) / 2)]);
        touche_move.point.push(touch_list[Math.floor(touch_list.length / 2)]);
        touche_move.point.push(touch_list[Math.floor(touch_list.length / 2) + Math.floor(Math.floor(touch_list.length / 2) / 2)]);
        touche_move.point.push(touch_list[touch_list.length - 1]);
      }
      var _0x19a192 = getFingerPrint();
      _0x15c802.client = "M";
      _0x15c802.clienttime = new Date().WebmFormatTime("yyyy-MM-dd hh:mm:ss");
      _0x15c802.hard_fingerprint = _0x19a192[0];
      _0x15c802.shshshfpa = _0x19a192[1];
      _0x15c802.pin = _0x32f026;
      _0x15c802.eventparam = touche_move;
      touch_list = [];
      var _0x14303a = {
        functionId: "STouch",
        info: _0x15c802
      };
      touche_move = {};
      body.push(_0x14303a);
      upload_data = getStorage("upload_data");
      if (upload_data != undefined) {
        if (upload_data.length >= 5) {
          body = [];
          setStorage("upload_data", body);
          sendMessage(upload_data, _0x19a192[2]);
          return;
        }
      }
      setStorage("upload_data", body);
    }
  } catch (_0x227b37) {}
}
function touchMove(_0x5105df) {
  _webmCallStackListener("touchMove");
  try {
    var _0x4c8d82 = _0x5105df.changedTouches[0];
    var _0x3e0a31 = _0x4c8d82.screenX + "_" + _0x4c8d82.screenY + "_" + _0x4c8d82.pageX + "_" + _0x4c8d82.pageY + "_" + new Date().getTime();
    touch_list.push(_0x3e0a31);
  } catch (_0x48bfc0) {}
}
function setStorage(_0x9dd287, _0x37fef8) {
  _webmCallStackListener("setStorage");
  try {
    if (window.localStorage) {
      localStorage.setItem(_0x9dd287, JSON.stringify(_0x37fef8));
    }
  } catch (_0x206a46) {}
}
function getStorage(_0x4c33b6) {
  _webmCallStackListener("getStorage");
  try {
    if (window.localStorage) {
      var _0x1b4896 = localStorage.getItem(_0x4c33b6);
      if (_0x1b4896) {
        return JSON.parse(_0x1b4896);
      }
      return undefined;
    }
    return undefined;
  } catch (_0x454618) {
    return undefined;
  }
}
function getCookie(_0x3370da) {
  _webmCallStackListener("getCookie");
  try {
    var _0x28b278 = new RegExp("(^| )" + _0x3370da + "(?:=([^;]*))?(;|$)");
    var _0x35a7be = document.cookie.match(_0x28b278);
    if (!_0x35a7be || !_0x35a7be[2] || _0x35a7be[2] == "undefined") {
      return "";
    }
    var _0x1a5d61 = _0x35a7be[2];
    if (/(%[0-9A-F]{2}){2,}/.test(_0x1a5d61)) {
      return decodeURIComponent(_0x1a5d61);
    } else {
      return unescape(_0x1a5d61);
    }
  } catch (_0xa93894) {
    return "";
  }
}