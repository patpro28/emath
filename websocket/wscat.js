#!/usr/bin/env node

/*!
 * ws: a node.js websocket client
 * Copyright(c) 2011 Einar Otto Stangvik <einaros@gmail.com>
 * MIT Licensed
 */

/**
 * Module dependencies.
 */

 var WebSocket = require('ws')
 , fs = require('fs')
 , program = require('commander')
 , util = require('util')
 , events = require('events')
 , readline = require('readline');

/**
* InputReader - processes console input
*/

function Console() {
 this.stdin = process.stdin;
 this.stdout = process.stdout;

 this.readlineInterface = readline.createInterface(this.stdin, this.stdout);

 var self = this;
 this.readlineInterface.on('line', function(data) {
   self.emit('line', data);
 });
 this.readlineInterface.on('close', function() {
   self.emit('close');
 });

 this._resetInput = function() {
   self.clear();
 }
}
util.inherits(Console, events.EventEmitter);

Console.Colors = {
 Red: '\033[31m',
 Green: '\033[32m',
 Yellow: '\033[33m',
 Cyan: '\033[36m',
 Blue: '\033[34m',
 Default: '\033[39m'
};

Console.prototype.prompt = function() {
 this.readlineInterface.prompt();
}

Console.prototype.print = function(msg, color) {
 this.clear();
 color = color || Console.Colors.Default;
 this.stdout.write(color + msg + Console.Colors.Default + '\n');
 this.prompt();
}

Console.prototype.clear = function() {
 this.stdout.write('\033[2K\033[E');
}

Console.prototype.pause = function() {
 this.stdin.on('keypress', this._resetInput);
}

Console.prototype.resume = function() {
 this.stdin.removeListener('keypress', this._resetInput);
}

function appender(xs) {
 xs = xs || [];
 return function (x) {
   xs.push(x);
   return xs;
 }
}

function into(obj, kvals) {
 kvals.forEach(function (kv) {
   obj[kv[0]] = kv[1];
 });
 return obj;
}

function splitOnce(sep, str) { // sep can be either String or RegExp
 var tokens = str.split(sep);
 return [tokens[0], str.replace(sep, '').substr(tokens[0].length)];
}

/**
* The actual application
*/

var version = '1.0';//JSON.parse(fs.readFileSync(__dirname + '/../package.json', 'utf8')).version;
program
 .version(version)
 .usage('[options] <url>')
 .option('-l, --listen <port>', 'listen on port')
 .option('-c, --connect <url>', 'connect to a websocket server')
 .option('-p, --protocol <version>', 'optional protocol version')
 .option('-o, --origin <origin>', 'optional origin')
 .option('--host <host>', 'optional host')
 .option('-s, --subprotocol <protocol>', 'optional subprotocol')
 .option('-n, --no-check', 'Do not check for unauthorized certificates')
 .option('-H, --header <header:value>', 'Set an HTTP header. Repeat to set multiple. (--connect only)', appender(), [])
 .option('--auth <username:password>', 'Add basic HTTP authentication header. (--connect only)')
 .parse(process.argv);

if (program.listen && program.connect) {
 console.error('\033[33merror: use either --listen or --connect\033[39m');
 process.exit(-1);
}
else if (program.listen) {
 var wsConsole = new Console();
 wsConsole.pause();
 var options = {};
 if (program.protocol) options.protocolVersion = program.protocol;
 if (program.origin) options.origin = program.origin;
 if (program.subprotocol) options.protocol = program.subprotocol;
 if (!program.check) options.rejectUnauthorized = program.check;
 var ws = null;
 var wss = new WebSocket.Server({port: program.listen}, function() {
   wsConsole.print('listening on port ' + program.listen + ' (press CTRL+C to quit)', Console.Colors.Green);
   wsConsole.clear();
 });
 wsConsole.on('close', function() {
   if (ws) {
     try {
       ws.close();
     }
     catch (e) {}
   }
   process.exit(0);
 });
 wsConsole.on('line', function(data) {
   if (ws) {
     ws.send(data, {mask: false});
     wsConsole.prompt();
   }
 });
 wss.on('connection', function(newClient) {
   if (ws) {
     // limit to one client
     newClient.terminate();
     return;
   };
   ws = newClient;
   wsConsole.resume();
   wsConsole.prompt();
   wsConsole.print('client connected', Console.Colors.Green);
   ws.on('close', function() {
     wsConsole.print('disconnected', Console.Colors.Green);
     wsConsole.clear();
     wsConsole.pause();
     ws = null;
   });
   ws.on('error', function(code, description) {
     wsConsole.print('error: ' + code + (description ? ' ' + description : ''), Console.Colors.Yellow);
   });
   ws.on('message', function(data, flags) {
     wsConsole.print('< ' + data, Console.Colors.Blue);
   });
 });
 wss.on('error', function(error) {
   wsConsole.print('error: ' + error.toString(), Console.Colors.Yellow);
   process.exit(-1);
 });
}
else if (program.connect) {
 var wsConsole = new Console();
 var options = {};
 if (program.protocol) options.protocolVersion = program.protocol;
 if (program.origin) options.origin = program.origin;
 if (program.subprotocol) options.protocol = program.subprotocol;
 if (program.host) options.host = program.host;
 if (!program.check) options.rejectUnauthorized = program.check;
 var headers = into({}, (program.header || []).map(function (s) {
                                                     return splitOnce(':', s)
                                                   }));
 if (program.auth) {
   headers['Authorization'] = 'Basic ' + new Buffer(program.auth).toString('base64');
 }
 options.headers = headers;
 var ws = new WebSocket(program.connect, options);
 ws.on('open', function() {
   wsConsole.print('connected (press CTRL+C to quit)', Console.Colors.Green);
   wsConsole.on('line', function(data) {
     ws.send(data, {mask: true});
     wsConsole.prompt();
   });
 });
 ws.on('close', function() {
   wsConsole.print('disconnected', Console.Colors.Green);
   wsConsole.clear();
   process.exit();
 });
 ws.on('error', function(code, description) {
   wsConsole.print('error: ' + code + (description ? ' ' + description : ''), Console.Colors.Yellow);
   process.exit(-1);
 });
 ws.on('message', function(data, flags) {
   wsConsole.print('< ' + data, Console.Colors.Cyan);
 });
 wsConsole.on('close', function() {
   if (ws) {
     try {
       ws.close();
     }
     catch(e) {}
     process.exit();
   }
 });
}
else {
 console.error('\033[33merror: use either --listen or --connect\033[39m');
 process.exit(-1);
}
