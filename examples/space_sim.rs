// A toy space simulation. It is intentionally *not* a compiling program --
// it only exists to show off gier/chier on realistic-looking Rust control
// flow (match guards, if-let, while-let, labeled loops, closures, async fn).

mod sim {
    use std::collections::HashMap;

    pub struct Body {
        pub pos: (f64, f64),
        pub vel: (f64, f64),
        pub mass: f64,
    }

    impl Body {
        pub fn step(&mut self, dt: f64) {
            self.pos.0 += self.vel.0 * dt;
            self.pos.1 += self.vel.1 * dt;
        }

        pub fn kinetic(&self) -> f64 {
            let v2 = self.vel.0 * self.vel.0 + self.vel.1 * self.vel.1;
            0.5 * self.mass * v2
        }
    }

    pub struct World {
        bodies: HashMap<u32, Body>,
    }

    impl World {
        pub fn new() -> Self {
            World { bodies: HashMap::new() }
        }

        pub async fn tick(&mut self, dt: f64) -> Result<(), SimError> {
            let snapshot: Vec<(u32, Body)> = self.bodies
                .iter()
                .map(|(id, b)| (*id, *b))
                .collect();

            'sim: for (id, body) in snapshot {
                if let Some(b) = self.bodies.get_mut(&id) {
                    b.step(dt);
                    match body.classify() {
                        Kind::Star if b.mass > 1e3 => continue 'sim,
                        Kind::Star => integrate_star(b, dt)?,
                        Kind::Planet => {
                            let pull = gravity(b)?;
                            while let Some(force) = pull.next() {
                                apply(force, b);
                            }
                        }
                        Kind::Comet => loop {
                            let d = drift(b);
                            if d < 1.0 {
                                break 'sim;
                            }
                            b.step(dt * 0.5);
                        },
                        _ => (),
                    }
                } else if body.is_dark() {
                    return Err(SimError::Missing(id));
                }
            }
            Ok(())
        }
    }

    fn gravity(b: &Body) -> Result<impl Iterator<Item = f64>, SimError> {
        Ok((0..3).map(move |i| b.pos.0 / (i as f64 + 1.0)))
    }

    fn integrate_star(b: &mut Body, dt: f64) -> Result<(), SimError> {
        let factor = match b.vel {
            (0.0, 0.0) => 1.0,
            _ => 2.0,
        };
        b.step(dt * factor);
        Ok(())
    }
}
