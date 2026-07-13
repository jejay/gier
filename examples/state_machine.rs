// A tiny state machine, also just for show (not a compiling program).
// Demonstrates an enum, a match with a guard, and a nested arm block.

enum State {
    Idle,
    Running { count: u32 },
    Done,
}

enum Event {
    Start,
    Tick,
    Reset,
}

impl State {
    pub fn advance(self, input: Event) -> State {
        match (self, input) {
            (State::Idle, Event::Start) => State::Running { count: 0 },
            (State::Running { count }, Event::Tick) if count < 10 => {
                let next = count + 1;
                State::Running { count: next }
            }
            (State::Running { .. }, Event::Tick) => State::Done,
            (State::Done, Event::Reset) => State::Idle,
            _ => self,
        }
    }

    pub fn is_active(&self) -> bool {
        matches!(self, State::Running { .. })
    }
}
