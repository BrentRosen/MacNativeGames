/* Real AppKit selector and profile persistence; simulated delayed controller enumeration. No game data/GPU work. */
#import <objc/runtime.h>
#include "../../runtime/gamepad.m"
#include "../../runtime/frontend.m"
#include <time.h>
_Noreturn void runtime_fail(const char *message){fprintf(stderr,"%s\n",message);exit(2);}
uint64_t runtime_now_ns(void){return clock_gettime_nsec_np(CLOCK_MONOTONIC);}
void runtime_feedback_attach(GCController *pad){(void)pad;}
void runtime_feedback_detach(GCController *pad){(void)pad;}
void runtime_feedback_quiet(void){}
@interface FakeController:NSObject
@property NSString *productCategory;
@property NSString *vendorName;
@property NSObject *extendedGamepad;
@end
@implementation FakeController
@end
static NSArray *pads;
static NSArray *controllers(id self,SEL sel){(void)self;(void)sel;return pads;}
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL: %s\n",#x);exit(1);}}while(0)
int main(int argc,const char **argv){@autoreleasepool{
 CHECK(argc==2);[NSApplication sharedApplication];
 CHECK(runtime_button_icons_choice()==0);
 NSMenu *bar=[NSMenu new];front_button_icons_add(bar);NSMenu *menu=bar.itemArray.lastObject.submenu;
 CHECK(menu.numberOfItems==7);CHECK([menu.itemArray[0].title isEqualToString:@"Automatic"]);
 CHECK(!menu.itemArray.lastObject.enabled);
 for(int i=0;i<5;i++){
  [buttonIconsMenu choose:menu.itemArray[i]];CHECK(runtime_button_icons_choice()==i);
  [buttonIconsMenu menuNeedsUpdate:menu];
  for(int j=0;j<5;j++)CHECK(menu.itemArray[j].state==(i==j?NSControlStateValueOn:NSControlStateValueOff));
  if(i)CHECK(strcmp(runtime_button_icons_style(),icon_choices[i])==0);
 }
 CHECK(!runtime_button_icons_set_choice(5));CHECK(runtime_button_icons_choice()==4);
 CHECK(runtime_button_icons_set_choice(0));
 CHECK([@"invalid" writeToFile:button_icons_path() atomically:YES encoding:NSUTF8StringEncoding error:nil]);
 CHECK(runtime_button_icons_choice()==0);
 CHECK(runtime_button_icons_set_choice(0));
 pads=@[];method_setImplementation(class_getClassMethod(GCController.class,@selector(controllers)),(IMP)controllers);
 started=YES;initialGamepad=dispatch_group_create();dispatch_group_enter(initialGamepad);
 const char *expected=argv[1];
 if(strcmp(expected,"keyboard"))dispatch_after(dispatch_time(DISPATCH_TIME_NOW,100*NSEC_PER_MSEC),dispatch_get_main_queue(),^{
  FakeController *pad=[FakeController new];pad.extendedGamepad=[NSObject new];
  pad.productCategory=!strcmp(expected,"playstation")?@"DualSense":!strcmp(expected,"switch")?@"Switch Pro Controller":@"Xbox One";
  pad.vendorName=@"Test controller";pads=@[pad];dispatch_group_leave(initialGamepad);
 });
 dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
  uint64_t at=runtime_now_ns();const char *style=runtime_button_icons_style();double elapsed=(runtime_now_ns()-at)/1e9;
  CHECK(!strcmp(style,expected));CHECK(elapsed<3);CHECK(elapsed>=(!strcmp(expected,"keyboard")?1.4:0.05));
  printf("pass: menu, saved choices, Automatic %s\n",style);exit(0);
 });
 [NSApp run];return 2;
}}
