# The ArduinoHttpClient library being used has some ERRORs
There are pull requests to fix these issues that havent been pulled yet. Not sure when they will fix them. Might want to fork it and apply fixes.
## Timed Read Error
Replace the line causing the error in HttpClient where the error occurs, not in stream:
```c++
int c;
bool timedout = true;
unsigned long startMillis = millis();
do {
    c = read();
    if (c >= 0) {
        timedout = false;
        break;
    }
    yield();
} while(millis() - startMillis < _timeout);

if (timedout) {
    // read timed out, done
    break;
}
```

## Logical Not Parentheses
Add the required parentheses.

```c++
if ((!iClient->connect(iServerName, iServerPort)) > 0)
```