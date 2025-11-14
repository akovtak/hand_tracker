//pan2 seems not to work cuz it needs mono signal
//add more synths
//control more parameters
///???
Server.killAll



(
s.options.sampleRate = 44100;
s.options.numWireBufs = 512;
s.options.memSize = 8192*5;


s.waitForBoot{





//switch
var window = Window("Switcher", Rect(200, 200, 220, 80)).front;
var view = CompositeView(window, Rect(0, 0, 220, 80));
//osc
var pv = Array.newClear(5);

Buffer.freeAll;
OSCdef.freeAll;
Synth.free;

~drums = Buffer.loadFolder(s, "C:/Users/sahsa/Desktop/sound/Balloons Sample Pack");

s.sync;







//SYNTHS

SynthDef(\grains, {|index=0.1, pR=0.1, tD=0, tF=20, amp=1, pan=0.0, active=0.0, modFreq=100.0|
	var sig;
	var trig = Dust.ar(tF); //100

	sig = Splay.ar(Mix.fill(5, {
		var freq = rrand(100,6000);
		//var modFreq = rrand(100,6000);
		PitchShift.ar(GrainFM.ar(2, trig, 0.02, freq, modFreq, index) * EnvGen.kr(Env.asr(1)) * 0.2, pitchRatio: pR, timeDispersion: tD) * amp.lag(0.1);
	}), center: -1.0);
	//sig = Pan2.ar(sig, pan);

	Out.ar(0, sig * active.lag(0.5))
}).add;

SynthDef(\resbass, {|res=1, low=0.1, hi=0.5, amp=1, freq=1.75, pan=0.0, active=0.0|
	var sig = Fold.ar(
		SinOscFB.ar(40, LFNoise1.ar(res).range(0.1,freq)) !2,
		low,
		hi.lag(1)
	) * EnvGen.kr(Env.asr(1)) * 0.6 * amp.lag(0.1);
	sig = Pan2.ar(sig, pan);

	Out.ar(0, sig * active.lag(0.5))
}).add;

SynthDef(\sinbass, {|f0=20, f1=20, f2=20, f3=20, f4=20, amp=1, pan=0.0, active=0.0|
	var sig = (Splay.ar(SinOsc.ar([f0, f1, f2, f3, f4])*0.15)) * EnvGen.kr(Env.asr(1)) * amp.lag(0.1) !2;
	//sig = Pan2.ar(sig, pan);

	Out.ar(0, sig * active.lag(0.5))
}).add;

SynthDef(\flanger, { |out = 0, in, mix = 1, amp = 1, maxDelayTime = 0.1,
	lfoFreq = 0.05, delayLo = 0.001, delayHi = 0.02, decayTime = 1, pan = 0, freq=50, active=0.0|
	//var sig, inSig = In.ar(in, 2);
	var sig, inSig;
	inSig = Saw.ar(freq.lag(1)) * EnvGen.kr(Env.asr(1)); //+ SinOsc.ar(60);
	sig = CombL.ar(
		inSig,
		maxDelayTime,
		{ LFDNoise3.ar(lfoFreq).range(delayLo, delayHi) } ! 2,
		decayTime
	) * mix + ((1 - mix) * (inSig*0.5));
	sig = Pan2.ar(sig[0], pan) + Pan2.ar(sig[1], pan.neg);
	sig = sig * amp.lag(0.1);

	XOut.ar(0, 1, (sig*0.1) * active.lag(0.5));
}).add;

SynthDef(\drums, {|bufnum1=0,trig=1,gate=1,amp=0.7,active=0.0,rate=1.0|
	Out.ar(0, (PlayBuf.ar(1,bufnum1,BufRateScale.kr(bufnum1)*rate,loop:0)!2 /** EnvGen.kr(Env.asr)*/) * amp * active)
}).add;

SynthDef(\bells, {|freq=500,gate=1,amp=0.25,velocity=0.01,active=0.0|
	var sig = CombN.ar(SinOsc.ar(freq)!2, 0.3, LFNoise2.ar(1).range(0.3,0.1), 2.0);
	sig = sig * EnvGen.kr(Env.perc, gate, doneAction:2) * amp;
	Out.ar(0,sig * active);
}).add;


s.sync;


a = [
	Synth(\grains),
	Synth(\resbass),
	Synth(\sinbass),
	Synth(\flanger),
	Synth(\drums, [bufnum1: ~drums[0]], addAction: \addToTail),
];



//KEYBOARD SWITHCER

view.background = Color.gray(0.18);
window.alwaysOnTop_(true);

view.canFocus = true;
view.focus;

view.keyDownAction_({ |v, char, mod, unicode, keycode|
	var idx = keycode - 49; // 49 -> 0 (key '1')
    if(idx.isInteger and: {idx.inclusivelyBetween(0, (a.size-1))}) {
        a.do(_.set(\active, 0));
        a[idx].set(\active, 1);
		a[idx].postln;
		~idx = idx;
    };
	if(keycode==54){
		Synth(\bells, [\active, 1]).postln;
		~bellsact = 1;
	}{
		Synth(\bells, [\active, 0]); ~bellsact = 0

	};
	if(keycode==48||keycode==54){
		a[~idx].set(\active, 0);
	};
});




s.sync;







//OSC

~oscrec = true;

OSCdef(\left, {|msg|
	var nv = msg[1..5];
	var diffs;

	if(~oscrec == true){
		a[0].set(\pR, msg[1].linlin(0.0,1,0.1,2));
		a[0].set(\tD, msg[2].linlin(0.0,1,0,0.2));
		a[0].set(\index, msg[3].linlin(0.0,1,0.1,10));
		a[0].set(\tF, msg[4].linlin(0.0,1,0.5,30));
		a[0].set(\modFreq, msg[5].linlin(0.0,1,100,6000));
		a[0].set(\pan, msg[7].linlin(0.0,1,-1.0,1.0));

		a[1].set(\res, msg[1].linlin(0.0,1,1,100));
		a[1].set(\hi, msg[2].linlin(0.0,1,0.5,1));
		a[1].set(\freq, msg[3].linlin(0.0,1,1.75,50));
		//a[1].set(\pan, msg[7].linlin(0.0,1,-1.0,1.0));

		a[2].set(\f0, msg[1].linlin(0.0,1,30,20));
		a[2].set(\f1, msg[2].linlin(0.0,1,40,20));
		a[2].set(\f2, msg[3].linlin(0.0,1,50,20));
		a[2].set(\f3, msg[4].linlin(0.0,1,40,20));
		a[2].set(\f4, msg[5].linlin(0.0,1,50,20));
		//a[2].set(\pan, msg[7].linlin(0.0,1,-1.0,1.0));

		a[3].set(\freq, msg[1].linlin(0.0,1,50,5000));
		a[3].set(\lfoFreq, msg[2].linlin(0.0,1,0.05,100));
		a[3].set(\decayTime, msg[3].linlin(0.0,1,0.1,2));
		a[3].set(\mix, msg[5]);

		if(pv[0].notNil){
			diffs = nv.collect{|val, i|
				if(val<0.19){val = 0.19};
				if(pv[i]<0.19){pv[i] = 0.19};
				if((val<0.2)&&(val != pv[i])){
					a[4].set(\bufnum1, rrand(0,~drums.size-1));
					if(~bellsact != 0){
						Synth(\bells, [\freq, rrand(500,2000), \active, 1], addAction: \addToTail);
					};
				};
			};
		};

		pv = nv;

	};

	//msg.round(0.01).postln;
}, '/hand/left');


OSCdef(\right, {|msg|

	a[0].set(\amp, msg[6].linlin(0.0,1,0.0,1));
	a[1].set(\amp, msg[6].linlin(0.0,1,0.0,1));
	a[2].set(\amp, msg[6].linlin(0.0,1,0.0,1));
	a[3].set(\amp, msg[6].linlin(0.0,1,0.0,1));
	a[4].set(\amp, msg[6].linlin(0.0,1,0.0,0.7));

    //msg.round(0.01).postln;
}, '/hand/right');
})






//freeze and unfreeze osc values
~oscrec = true;
~oscrec = false;


