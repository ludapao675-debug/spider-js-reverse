require=(function(){function r(e,n,t){function o(i,f){if(!n[i]){if(!e[i]){var c="function"==typeof require&&require;if(!f&&c)return c(i,!0);if(u)return u(i,!0);var a=new Error("Cannot find module '"+i+"'");throw a.code="MODULE_NOT_FOUND",a}var p=n[i]={exports:{}};e[i][0].call(p.exports,function(r){var n=e[i][1][r];return o(n||r)},p,p.exports,r,e,n,t)}return n[i].exports}for(var u="function"==typeof require&&require,i=0;i<t.length;i++)o(t[i]);return o}return r})()({50:[function(require,module,exports){
//var sign = require('./sign');
var csrf = $('#csrf').text();

$.ajaxSettings.beforeSend = function(xhr, settings) {
    var url = settings.url || '';
    var loganUrl = 'logan.sankuai.com';
    if (window.mtUnitLoginEnv === 'test') {
        loganUrl = 'logan.plat.test.sankuai.com';
    }
    if(url.indexOf(loganUrl) > -1) {
        return;
    }
    xhr.setRequestHeader('X-Client', 'javascript');
    xhr.setRequestHeader('X-CSRF-Token', csrf);
    //var method = settings.method;
    //var url = settings.url;
    //var date = (new Date).toGMTString();
    //var authorization;
    //try {
        //authorization = sign(date, method, url);
    //} catch(err) {
        //xhr.setRequestHeader('X-Error', err.name + ' ' + err.message);
    //}
    //xhr.setRequestHeader('X-Date', date);
    //xhr.setRequestHeader('X-Authorization', authorization);
}

},{}]},{},[50]);
