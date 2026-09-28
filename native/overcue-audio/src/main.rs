// SPDX-License-Identifier: MPL-2.0
// Experimental offline preparation. Never used by the deck audio callback.
use ebur128::{EbuR128, Mode};
use std::{
    env,
    fs::{File, OpenOptions},
    io::{BufReader, BufWriter, Read, Write},
};
fn measure(path: &str) -> Result<(), Box<dyn std::error::Error>> {
    let mut src = BufReader::new(File::open(path)?);
    let mut meter = EbuR128::new(
        2,
        96000,
        Mode::M | Mode::S | Mode::SAMPLE_PEAK | Mode::TRUE_PEAK,
    )?;
    let mut ring = [0.0f64; 30];
    let mut number = 0usize;
    loop {
        let mut bytes = vec![0u8; 9600 * 8];
        let mut used = 0;
        while used < bytes.len() {
            let n = src.read(&mut bytes[used..])?;
            if n == 0 {
                break;
            }
            used += n;
        }
        if used == 0 {
            break;
        }
        if used % 8 != 0 {
            return Err("partial frame".into());
        }
        let samples: Vec<f32> = bytes[..used]
            .chunks_exact(4)
            .map(|c| f32::from_le_bytes(c.try_into().unwrap()))
            .collect();
        if samples.iter().any(|v| !v.is_finite()) {
            return Err("nonfinite sample".into());
        }
        meter.add_frames_f32(&samples)?;
        let (m, s) = if used == bytes.len() {
            let l = meter.loudness_window(100)?;
            ring[number % 30] = 10.0f64.powf((l + 0.691) / 10.0);
            let mut m = 0.0;
            let mut s = 0.0;
            for age in 0..30 {
                let e = ring[(number + 30 - age) % 30];
                s += e;
                if age < 4 {
                    m += e;
                }
            }
            (
                10.0 * (m / 4.0).log10() - 0.691,
                10.0 * (s / 30.0).log10() - 0.691,
            )
        } else {
            (meter.loudness_momentary()?, meter.loudness_shortterm()?)
        };
        println!("window {} {} {}", m, s, used == bytes.len());
        number += 1;
    }
    let peak = meter
        .sample_peak(0)?
        .max(meter.sample_peak(1)?)
        .max(meter.true_peak(0)?)
        .max(meter.true_peak(1)?);
    println!("peak {}", peak);
    Ok(())
}

fn read_floats(path: &str) -> Result<Vec<f32>, Box<dyn std::error::Error>> {
    let data = std::fs::read(path)?;
    if data.is_empty() || data.len() % 8 != 0 {
        return Err("nonempty stereo f32le required".into());
    }
    let values: Vec<f32> = data
        .chunks_exact(4)
        .map(|c| f32::from_le_bytes(c.try_into().unwrap()))
        .collect();
    if values.iter().any(|v| !v.is_finite()) {
        return Err("nonfinite float".into());
    }
    Ok(values)
}
fn resample(
    input: &str,
    output: &str,
    coefficients: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let x = read_floats(input)?;
    let h = read_floats(coefficients)?;
    if h.len() != 320 * 59 {
        return Err("320 phases of 59 taps required".into());
    }
    let frames = x.len() / 2;
    let count = frames.checked_mul(320).ok_or("input too large")? / 147;
    let mut out = BufWriter::new(OpenOptions::new().write(true).create_new(true).open(output)?);
    let mut peak = 0.0f32;
    for j in 0..count {
        let center = j * 147 / 320;
        let phase = j * 147 % 320;
        for channel in 0..2 {
            let mut sum = -0.0f64;
            if center >= 58 && center < frames {
                for k in (0..59).rev() {
                    sum += (x[2 * (center - k) + channel] as f64) * (h[k * 320 + phase] as f64);
                }
            } else {
                for k in 0..59 {
                    if k <= center && center - k < frames {
                        sum += (x[2 * (center - k) + channel] as f64) * (h[k * 320 + phase] as f64);
                    }
                }
            }
            let value = sum as f32;
            peak = peak.max(value.abs());
            out.write_all(&value.to_le_bytes())?;
        }
    }
    out.flush()?;
    println!("peak {}", peak);
    Ok(())
}
fn quantize(input: &str, output: &str, gain: &str) -> Result<(), Box<dyn std::error::Error>> {
    let gain: f32 = gain.parse()?;
    if !gain.is_finite() || !(0.0..=1.0).contains(&gain) {
        return Err("invalid gain".into());
    }
    let mut input = BufReader::new(File::open(input)?);
    let mut out = BufWriter::new(OpenOptions::new().write(true).create_new(true).open(output)?);
    let mut frame = [0u8; 8];
    loop {
        let n = input.read(&mut frame[..1])?;
        if n == 0 {
            break;
        }
        input.read_exact(&mut frame[1..])?;
        for channel in frame.chunks_exact(4) {
            let value = f32::from_le_bytes(channel.try_into().unwrap());
            if !value.is_finite() {
                return Err("nonfinite float".into());
            }
            let value = (((value * gain).clamp(-1.0, 1.0) * 32767.0).round()) as i16;
            out.write_all(&value.to_le_bytes())?;
        }
    }
    out.flush()?;
    Ok(())
}
fn main() {
    let args: Vec<String> = env::args().collect();
    let result=match args.get(1).map(String::as_str) {
  Some("measure") if args.len()==3 => measure(&args[2]),
  Some("resample") if args.len()==5 => resample(&args[2],&args[3],&args[4]),
  Some("quantize") if args.len()==5 => quantize(&args[2],&args[3],&args[4]),
  _ => Err("usage: rx3-overcue-audio measure INPUT | resample INPUT OUTPUT COEFFICIENTS | quantize INPUT OUTPUT GAIN".into())
 };
    if let Err(error) = result {
        eprintln!("{}", error);
        std::process::exit(2);
    }
}
