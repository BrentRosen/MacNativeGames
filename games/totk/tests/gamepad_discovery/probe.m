/* Exercise the real icon selector with controller notifications delayed until the main loop runs. */
#import <objc/runtime.h>
#include "../../runtime/gamepad.m"
#include <time.h>

_Noreturn void runtime_fail(const char *message) { fprintf(stderr,"%s\n",message); exit(2); }
uint64_t runtime_now_ns(void) { return clock_gettime_nsec_np(CLOCK_MONOTONIC); }
void runtime_feedback_attach(GCController *controller) { (void)controller; }
void runtime_feedback_detach(GCController *controller) { (void)controller; }
void runtime_feedback_quiet(void) {}

@interface TestController : NSObject
@property NSString *productCategory;
@property NSString *vendorName;
@property NSObject *extendedGamepad;
@end
@implementation TestController
@end
static NSArray *testControllers;
static NSArray *controllers(id self, SEL selector) { (void)self; (void)selector; return testControllers; }

int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc!=2) return 2;
        const char *expected=argv[1];
        testControllers=@[];
        method_setImplementation(class_getClassMethod(GCController.class,@selector(controllers)),(IMP)controllers);
        started=YES; initialGamepad=dispatch_group_create(); dispatch_group_enter(initialGamepad);
        if (strcmp(expected,"keyboard")) {
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW,100*NSEC_PER_MSEC),dispatch_get_main_queue(),^{
                TestController *pad=[TestController new];pad.extendedGamepad=[NSObject new];
                pad.productCategory=!strcmp(expected,"playstation")?@"DualSense":
                                    !strcmp(expected,"switch")?@"Switch Pro Controller":@"Xbox One";
                pad.vendorName=@"Test controller";testControllers=@[pad];
                dispatch_group_leave(initialGamepad);
            });
        }
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
            uint64_t before=runtime_now_ns();
            const char *style=runtime_gamepad_icon_style();
            double elapsed=(runtime_now_ns()-before)/1e9;
            int ok=!strcmp(style,expected) && elapsed>=(!strcmp(expected,"keyboard")?1.4:0.05) && elapsed<3;
            printf("{\"style\":\"%s\",\"seconds\":%.3f,\"status\":\"%s\"}\n",style,elapsed,ok?"pass":"fail");
            exit(ok?0:1);
        });
        dispatch_main();
    }
}
